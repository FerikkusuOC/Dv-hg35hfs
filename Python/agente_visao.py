import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import requests
import re
import time
import platform
from configuracoes import DEBUG_MODE

# --- DETECÇÃO DE SISTEMA E MODELO ---
SISTEMA = platform.system()
# A GPU T4 do Colab (Linux) lida perfeitamente com o 3b sem estourar o contexto.
MODELO_VISAO = "frob/qwen3.5-instruct:9b" if SISTEMA == "Linux" else "frob/qwen3.5-instruct:9b"

def descarregar_modelo(nome_modelo=MODELO_VISAO):
    """Remove o modelo da VRAM para liberar espaço. Atua como um 'Desfibrilador'."""
    if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] Limpando {nome_modelo} da VRAM...")
    try:
        requests.post("http://127.0.0.1:11434/api/chat", json={"model": nome_modelo, "keep_alive": 0}, timeout=5)
    except:
        pass

def gerar_grid_3x3_base64(caminho_imagem):
    try:
        img = Image.open(caminho_imagem).convert('RGB')
        w_orig, h_orig = img.size
        
        # COMPRESSÃO AGRESSIVA (Para evitar Context Overflow no Ollama)
        max_size = 480
        if w_orig > h_orig:
            novo_w, novo_h = max_size, int((h_orig / w_orig) * max_size)
        else:
            novo_w, novo_h = int((w_orig / h_orig) * max_size), max_size
            
        img = img.resize((novo_w, novo_h), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        passo_x, passo_y = novo_w // 3, novo_h // 3
        
        try: fonte = ImageFont.truetype("arial.ttf", 24)
        except: fonte = ImageFont.load_default()
        
        for i in range(1, 3):
            draw.line([(0, passo_y*i), (novo_w, passo_y*i)], fill="red", width=2)
            draw.line([(passo_x*i, 0), (passo_x*i, novo_h)], fill="red", width=2)
        
        contador = 1
        for y in range(3):
            for x in range(3):
                px, py = (x * passo_x) + (passo_x // 2) - 8, (y * passo_y) + (passo_y // 2) - 8
                draw.rectangle([px-3, py-3, px+20, py+20], fill="black")
                draw.text((px, py), str(contador), fill="white", font=fonte)
                contador += 1
                
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=75) 
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        if DEBUG_MODE: print(f"      [DEBUG] Erro ao gerar grid focal: {e}")
        return ""

def esmagar_base64_existente(b64_string):
    """Garante que qualquer imagem enviada à IA seja esmagada para ~480x270."""
    try:
        img_bytes = base64.b64decode(b64_string)
        img = Image.open(BytesIO(img_bytes)).convert('RGB')
        
        w, h = img.size
        if w > h:
            img = img.resize((480, int((h/w)*480)), Image.Resampling.LANCZOS)
        else:
            img = img.resize((int((w/h)*480), 480), Image.Resampling.LANCZOS)
            
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except:
        return b64_string

def extrair_numeros_seguros(texto, limite=1):
    texto_limpo = re.sub(r'[@#\$%\^&\*\(\)<>=\+\{\};!]', ' ', texto)
    numeros_brutos = [int(n) for n in re.findall(r'[1-9]', texto_limpo)]
    if not numeros_brutos: return []
    numeros_unicos = list(dict.fromkeys(numeros_brutos))
    return numeros_unicos[:limite]

def escolher_imagem_ia_base64(query, b64_img, id_cena="Desconhecida"):
    # TESOURA DE SEGURANÇA: Limita a query a 150 caracteres para evitar o Context Overflow
    query_segura = query[:150] + "..." if len(query) > 150 else query
    
    if DEBUG_MODE: print(f"      [DEBUG] [Visão Curadoria] [CENA {id_cena}] A analisar grid para '{query_segura}'")
    b64_desidratado = esmagar_base64_existente(b64_img)

    prompt = (
        f"Task: Match the text to the correct image.\n"
        f"Text: '{query_segura}'\n"
        f"Look at the 5 numbered images. Which number best matches the text?\n"
        f"Answer with exactly ONE digit. Example: 3\n"
        f"[Trace ID: {time.time()}]"
    )

    for tentativa in range(2):
        payload = {
            "model": MODELO_VISAO,
            "messages": [
                {"role": "system", "content": "You are a rigid number extractor. Output only digits."},
                {"role": "user", "content": prompt, "images": [b64_desidratado]}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 4, 
                "stop": ["\n", " ", "<|im_end|>", "<|endoftext|>"]
            }
        }

        try:
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=40)
            if res.status_code == 200:
                resposta_ia = res.json().get("message", {}).get("content", "").strip()
                if DEBUG_MODE: print(f"      [DEBUG] [CENA {id_cena}] Resposta bruta ({MODELO_VISAO}): '{resposta_ia}'")
                
                numeros_encontrados = extrair_numeros_seguros(resposta_ia, limite=1)
                texto_numeros = re.sub(r'[^0-9]', '', resposta_ia)
                is_alucinacao = len(texto_numeros) >= 3 and len(set(texto_numeros)) == 1

                if is_alucinacao or not numeros_encontrados or numeros_encontrados[0] > 5:
                    if tentativa == 1:
                        if DEBUG_MODE: print(f"      [DEBUG] [Aviso] Falha na cena {id_cena}. Assumindo candidato 1.")
                        return 1
                    
                    if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] IA alucinou. Ejetando modelo da VRAM e tentando de novo...")
                    descarregar_modelo()
                    time.sleep(2)
                    continue 

                return numeros_encontrados[0]
            else:
                if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] Servidor retornou código {res.status_code}. Limpando VRAM...")
                descarregar_modelo()
                time.sleep(2)
                
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] [Erro Conexão] [CENA {id_cena}]: {e}")
            if tentativa == 1:
                return 1
            if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] Timeout detectado. Limpando VRAM e reiniciando a chamada...")
            descarregar_modelo()
            time.sleep(2)
            
    return 1

def analisar_ponto_focal(b64_img, texto_cena, query, id_cena="Desconhecida"):
    if DEBUG_MODE: print(f"      [DEBUG] [Visão Focal] [CENA {id_cena}] Iniciando análise de foco...")
    
    # TESOURA DE SEGURANÇA: Limita o contexto a no máximo 150 caracteres para não estourar a mente da IA
    texto_seguro = texto_cena[:150] + "..." if len(texto_cena) > 150 else texto_cena
    
    prompt = f"""Task: Find the focal point of the 'Visual Target' in the 3x3 grid.
Context: '{texto_seguro}'
Visual Target: '{query}'

RULES:
- If the target is a character, locate their FACE/EYES.
- If it is an object, locate its CENTER.
- BE PRECISE: 1 single box is the best answer. Use 2 or 3 boxes ONLY if the target is huge and spreads across them. NEVER use more than 3 boxes.

Format: Only digits and commas.
Good Example A: 5
Good Example B: 2, 5

[Trace ID: {time.time()}]
Output:"""

    for tentativa in range(2):
        payload = {
            "model": MODELO_VISAO,
            "messages": [
                {"role": "system", "content": "You are a rigid number extractor. Output only digits."},
                {"role": "user", "content": prompt, "images": [b64_img]}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0, 
                "num_predict": 10,
                "stop": ["\n", "<|im_end|>", "<|endoftext|>"]
            }
        }

        try:
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=40)
            if res.status_code == 200:
                resposta_ia = res.json().get("message", {}).get("content", "").strip()
                if DEBUG_MODE: print(f"      [DEBUG] [CENA {id_cena}] Resposta bruta ({MODELO_VISAO}): '{resposta_ia}'")
                
                numeros_encontrados = extrair_numeros_seguros(resposta_ia, limite=3)
                texto_numeros = re.sub(r'[^0-9]', '', resposta_ia)
                is_alucinacao = len(texto_numeros) >= 5 and len(set(texto_numeros)) == 1

                if is_alucinacao or not numeros_encontrados:
                    if tentativa == 1:
                        if DEBUG_MODE: print(f"      [DEBUG] [Aviso] Falha na cena {id_cena}. Trancando no centro [5].")
                        return [5]
                    
                    if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] IA alucinou. Ejetando modelo da VRAM e tentando de novo...")
                    descarregar_modelo()
                    time.sleep(2)
                    continue 
                    
                if DEBUG_MODE: print(f"      [DEBUG] [Visão Focal] [CENA {id_cena}] Alvo trancado: {numeros_encontrados}")
                return numeros_encontrados
            else:
                if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] Servidor retornou código {res.status_code}. Limpando VRAM...")
                descarregar_modelo()
                time.sleep(2)
                
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] [Erro Conexão] [CENA {id_cena}]: {e}")
            if tentativa == 1:
                return [5]
            if DEBUG_MODE: print(f"      [DEBUG] [Desfibrilador] Timeout detectado. Limpando VRAM e reiniciando a chamada...")
            descarregar_modelo()
            time.sleep(2)
            
    return [5]