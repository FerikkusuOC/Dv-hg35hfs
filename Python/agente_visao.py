import json
import re
import time
import requests
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

from configuracoes import *

def codificar_imagem_base64_comprimida(caminho_imagem):
    img = Image.open(caminho_imagem)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.thumbnail((600, 600)) 
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=70) 
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def escolher_imagem_ia_base64(query_cena, img_b64):
    prompt_visao = f"You are a strict image classifier. Look at the numbered grid. Which image number (1, 2, 3, 4, or 5) best matches the description '{query_cena}'? Output exactly ONE single digit and absolutely nothing else."
    
    if DEBUG_MODE: print(f"      [DEBUG] [Visão Curadoria] A analisar grelha para '{query_cena}'...")
    max_tentativas = 2
    
    for tentativa in range(max_tentativas):
        try:
            payload = {
                "model": "qwen2.5vl:3b",
                "messages": [{"role": "user", "content": prompt_visao, "images": [img_b64]}],
                "stream": False, "keep_alive": "5m", "options": {"temperature": 0.0}
            }
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=120)
            
            # Se o Ollama der qualquer erro (Ex: 404 Model Not Found), ele IMPRIME NA TELA agora!
            if res.status_code != 200:
                print(f"      [ERRO EXATO DA API OLLAMA - Curadoria]: HTTP {res.status_code} - {res.text}")
                res.raise_for_status()
            
            texto_ia = res.json().get('message', {}).get('content', '')
            num = re.search(r'[1-5]', texto_ia)
            if num:
                return int(num.group())
            else:
                print(f"      [ERRO EXATO DA IA VISÃO - Curadoria]: Resposta fora do padrão: '{texto_ia}'")
                
        except Exception as e:
            print(f"      [ERRO EXATO DO CÓDIGO - Curadoria]: {e}")
            if tentativa < max_tentativas - 1:
                time.sleep(2)
            else:
                if DEBUG_MODE: print("      [DEBUG] [Fallback] IA incapaz de decidir após 2 tentativas. Imagem 1 assumida.")
                return 1

def gerar_grid_3x3_base64(caminho_img_original):
    try:
        img = Image.open(caminho_img_original).convert('RGB')
        w, h = img.size
        draw = ImageDraw.Draw(img)
        try: fonte = ImageFont.truetype("arial.ttf", int(h/8))
        except: fonte = ImageFont.load_default()

        step_x = w / 3
        step_y = h / 3

        draw.line([(step_x, 0), (step_x, h)], fill="red", width=5)
        draw.line([(step_x*2, 0), (step_x*2, h)], fill="red", width=5)
        draw.line([(0, step_y), (w, step_y)], fill="red", width=5)
        draw.line([(0, step_y*2), (w, step_y*2)], fill="red", width=5)

        num = 1
        for y in range(3):
            for x in range(3):
                cx = int(x * step_x + step_x / 2)
                cy = int(y * step_y + step_y / 2)
                draw.rectangle([cx-40, cy-40, cx+40, cy+40], fill="black")
                draw.text((cx, cy), str(num), fill="red", font=fonte, anchor="mm")

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=70)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"      [ERRO EXATO DO CÓDIGO - Geração Grid]: {e}")
        return None

def analisar_ponto_focal(img_b64_com_grid, texto_cena, query):
    prompt = f"Look at the red 3x3 grid (numbered 1 to 9) on this image. NARRATION: '{texto_cena}'. TASK: Identify the EXACT grid number(s) containing the CORE focal point. Return ONLY a raw JSON array of integers. Example: [2] or [4, 5]."

    if DEBUG_MODE: print("      [DEBUG] [Visão Focal] Analisando enquadramento...")
    
    for tentativa in range(2):
        try:
            payload = {
                "model": "qwen2.5vl:3b",
                "messages": [{"role": "user", "content": prompt, "images": [img_b64_com_grid]}],
                "stream": False, "keep_alive": "5m", "options": {"temperature": 0.0, "num_predict": 30}
            }
            res = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=120)
            
            if res.status_code != 200:
                print(f"      [ERRO EXATO DA API OLLAMA - Foco]: HTTP {res.status_code} - {res.text}")
                res.raise_for_status()
            
            texto_ia = res.json().get('message', {}).get('content', '').strip()
            
            match = re.search(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', texto_ia)
            if match:
                quadros = json.loads(match.group(0))
                if isinstance(quadros, list) and len(quadros) > 0:
                    return quadros[:3]
            
            digitos_soltos = [int(d) for d in re.findall(r'[1-9]', texto_ia)]
            if digitos_soltos:
                return list(set(digitos_soltos[:3]))
            
            print(f"      [ERRO EXATO DA IA VISÃO - Foco]: Resposta fora do padrão: '{texto_ia}'")
            time.sleep(2)
            
        except Exception as e:
            print(f"      [ERRO EXATO DO CÓDIGO - Foco]: {e}")
            time.sleep(2)
            
    return [5]
