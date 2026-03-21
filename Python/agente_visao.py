import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import requests
import re
import time
import threading
from configuracoes import DEBUG_MODE

MODELO_VISAO = "qwen2.5vl:3b"

lock_reset = threading.Lock()
ultimo_reset = 0.0

def resetar_modelo_seguro():
    global ultimo_reset
    with lock_reset:
        tempo_atual = time.time()
        if tempo_atual - ultimo_reset > 15.0:
            if DEBUG_MODE: print(f"\n      [!!!] [ALERTA] VRAM congestionada. A forçar esvaziamento total...")
            try:
                requests.post("http://127.0.0.1:11434/api/chat", json={"model": MODELO_VISAO, "keep_alive": 0}, timeout=10)
                time.sleep(3.0) 
            except: pass
            ultimo_reset = time.time()
            if DEBUG_MODE: print(f"      [!!!] VRAM limpa. Retomando operações.\n")
        else:
            time.sleep(2.0)

def gerar_grid_3x3_base64(caminho_imagem):
    try:
        img = Image.open(caminho_imagem).convert('RGB')
        img = img.resize((480, 270), Image.NEAREST)
        
        draw = ImageDraw.Draw(img)
        w, h = img.size
        passo_x, passo_y = w // 3, h // 3
        
        try: fonte = ImageFont.truetype("arial.ttf", 20)
        except: fonte = ImageFont.load_default()
        
        for i in range(1, 3):
            draw.line([(0, passo_y*i), (w, passo_y*i)], fill="red", width=2)
            draw.line([(passo_x*i, 0), (passo_x*i, h)], fill="red", width=2)
        
        contador = 1
        for y in range(3):
            for x in range(3):
                px = (x * passo_x) + (passo_x // 2) - 8
                py = (y * passo_y) + (passo_y // 2) - 8
                draw.rectangle([px-3, py-3, px+18, py+18], fill="black")
                draw.text((px, py), str(contador), fill="white", font=fonte)
                contador += 1
                
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=40) 
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        if DEBUG_MODE: print(f"      [DEBUG] Erro ao gerar grid focal: {e}")
        return ""

def esmagar_base64_existente(b64_string):
    try:
        # 1. LIMPEZA: Remove sujeiras do .txt que fazem o b64decode quebrar
        b64_limpo = b64_string.replace('\n', '').replace('\r', '').strip()
        if "," in b64_limpo:
            b64_limpo = b64_limpo.split(",")[-1]
            
        # Repara o padding caso o arquivo texto tenha cortado o final
        padding = len(b64_limpo) % 4
        if padding > 0:
            b64_limpo += '=' * (4 - padding)

        img_bytes = base64.b64decode(b64_limpo)
        img = Image.open(BytesIO(img_bytes)).convert('RGB')
        
        # 2. REDUÇÃO DRÁSTICA: De 1200x800 para 480x320 (Mesmo peso matemático do Foco)
        img = img.resize((480, 320), Image.NEAREST)
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=40)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        if DEBUG_MODE: print(f"      [DEBUG] [Aviso] Falha ao comprimir Base64: {e}. Enviando imagem bruta...")
        return b64_string

def extrair_numeros_seguros(texto, limite=1):
    texto_limpo = re.sub(r'[@#\$%\^&\*\(\)<>=\+\{\};!]', ' ', texto)
    numeros = [int(n) for n in re.findall(r'[1-9]', texto_limpo)]
    if not numeros: return []
    return numeros[:limite]

def escolher_imagem_ia_base64(query, b64_img):
    if DEBUG_MODE: print(f"      [DEBUG] [Visão Curadoria] A analisar grelha para '{query}'...")
    
    b64_desidratado = esmagar_base64_existente(b64_img)

    prompt_curadoria = (
        f"Analyze the attached grid of 5 numbered images.\n"
        f"Which image number best matches this description: '{query}'?\n"
        f"Reply ONLY with a single digit from 1 to 5. No explanations."
    )

    payload = {
        "model": MODELO_VISAO,
        "messages": [{"role": "user", "content": prompt_curadoria, "images": [b64_desidratado]}],
        "stream": False,
        "options": {
            "temperature": 0.2, 
            "num_predict": 20
        }
    }

    for tentativa in range(2):
        try:
            # 60 segundos de fôlego para evitar o Timeout prematuro
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=60)
            if res.status_code == 200:
                resposta_ia = res.json().get("message", {}).get("content", "").strip()
                
                numeros_encontrados = extrair_numeros_seguros(resposta_ia, limite=1)
                
                if "!!!" in resposta_ia or not numeros_encontrados or numeros_encontrados[0] > 5:
                    if DEBUG_MODE: print(f"      [DEBUG] [Aviso] Alucinação detetada na curadoria. A acionar protocolo de segurança (Tentativa {tentativa+1}/2)")
                    resetar_modelo_seguro()
                    continue
                    
                return numeros_encontrados[0]
            else:
                time.sleep(1)
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] [Erro Visão Curadoria] Falha com Ollama: {e}")
            resetar_modelo_seguro()
            
    if DEBUG_MODE: print("      [DEBUG] [Fallback] IA incapaz de decidir após 2 tentativas. Imagem 1 assumida.")
    return 1

def analisar_ponto_focal(b64_img, texto_cena, query):
    prompt_foco = (
        f"Context: '{texto_cena}'. Target: '{query}'.\n"
        f"Analyze the attached 3x3 grid numbered 1 to 9.\n"
        f"Which grid numbers contain the main character's face or the main action?\n"
        f"Reply ONLY with the numbers. Example: 2, 3"
    )

    payload = {
        "model": MODELO_VISAO,
        "messages": [{"role": "user", "content": prompt_foco, "images": [b64_img]}],
        "stream": False,
        "options": {
            "temperature": 0.2, 
            "num_predict": 20
        }
    }

    for tentativa in range(2):
        try:
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=60)
            if res.status_code == 200:
                resposta_ia = res.json().get("message", {}).get("content", "").strip()
                
                numeros_encontrados = extrair_numeros_seguros(resposta_ia, limite=3)
                
                if "!!!" in resposta_ia or not numeros_encontrados:
                    if DEBUG_MODE: print(f"      [DEBUG] [Aviso] Alucinação detetada no foco. A acionar protocolo de segurança (Tentativa {tentativa+1}/2)")
                    resetar_modelo_seguro()
                    continue
                    
                if DEBUG_MODE: print(f"      [DEBUG] [Visão Focal] Alvo trancado nos quadros: {numeros_encontrados}")
                return numeros_encontrados
            else:
                time.sleep(1)
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] [Erro Visão Foco] Falha com Ollama: {e}")
            resetar_modelo_seguro()
            
    return [5]
