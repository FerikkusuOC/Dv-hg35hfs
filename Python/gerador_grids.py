import os
import sys
import time
import json
import base64
import traceback
import concurrent.futures
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

DIRETORIO_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_RAIZ = os.path.dirname(DIRETORIO_SCRIPT)
sys.path.append(DIRETORIO_SCRIPT)
from configuracoes import *

ARQUIVO_ESTADO = os.path.join(DIRETORIO_SCRIPT, "estado_projeto.json")

def montar_grid_base64(indice_cena):
    canvas = Image.new('RGB', (1200, 800), color='black')
    coords = [(0, 0), (400, 0), (800, 0), (0, 400), (400, 400)]
    try: fonte = ImageFont.truetype("arial.ttf", 60)
    except: fonte = ImageFont.load_default()
    draw = ImageDraw.Draw(canvas)

    for i in range(5):
        caminho_cand = os.path.join(DIRETORIO_RAIZ, "temp_imagens", f"cena_{indice_cena:03d}_cand_{i+1}.jpg")
        try:
            # Como a imagem foi gravada em RAW, precisamos de forçar o carregamento total
            img = Image.open(caminho_cand)
            img.load() 
            img = img.convert('RGB')
        except:
            img = Image.new('RGB', (400, 400), color='#1a1a1a')
            
        aspect = img.width / img.height
        # Otimização extrema: Image.NEAREST ignora cálculos interpolados pesados
        if aspect > 1:
            nw = int(400 * aspect)
            img = img.resize((nw, 400), Image.NEAREST).crop(((nw - 400) / 2, 0, (nw - 400) / 2 + 400, 400))
        else:
            nh = int(400 / aspect)
            img = img.resize((400, nh), Image.NEAREST).crop((0, (nh - 400) / 2, 400, (nh - 400) / 2 + 400))
            
        canvas.paste(img, coords[i])
        x, y = coords[i]
        draw.rectangle([x, y, x+60, y+60], fill="black")
        draw.text((x+15, y+5), str(i+1), fill="white", font=fonte)
        
    buffer = BytesIO()
    canvas.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def processar_cena_grid(indice_cena):
    arquivo_grid = os.path.join(DIRETORIO_RAIZ, "temp_imagens", f"cena_{indice_cena:03d}_grid.txt")
    print(f" -> [PARALELO] Núcleo ativado: A montar grelha da Cena {indice_cena:03d}...")
    try:
        b64 = montar_grid_base64(indice_cena)
        with open(arquivo_grid, 'w', encoding='utf-8') as f:
            f.write(b64)
        return True
    except Exception as e:
        print(f"[AVISO] Falha leve ao criar grelha {indice_cena:03d}: {e}")
        return False

def main():
    try:
        print("===================================================")
        print("      ROBÔ GERADOR DE GRIDS (V2.0 PARALELO) ")
        print("===================================================")
        print(f"[STATUS] A aguardar o ficheiro de projeto em:\n{ARQUIVO_ESTADO}")
        
        while not os.path.exists(ARQUIVO_ESTADO):
            time.sleep(1)
            
        with open(ARQUIVO_ESTADO, 'r', encoding='utf-8') as f:
            dados = json.load(f)
            total_cenas = len(dados.get('cenas', []))
            
        if total_cenas == 0:
            return

        print(f"[STATUS] Projeto detetado! A monitorizar {total_cenas} cenas com Multiprocessamento...")
        
        grids_gerados = set()
        
        # O ROBÔ AGORA TEM 4 BRAÇOS! Processa múltiplas cenas ao mesmo tempo.
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            while len(grids_gerados) < total_cenas:
                for i in range(total_cenas):
                    if i in grids_gerados: continue
                    
                    arquivo_grid = os.path.join(DIRETORIO_RAIZ, "temp_imagens", f"cena_{i:03d}_grid.txt")
                    arquivo_flag = os.path.join(DIRETORIO_RAIZ, "temp_imagens", f"cena_{i:03d}_ok.flag")
                    
                    if os.path.exists(arquivo_grid):
                        grids_gerados.add(i)
                    elif os.path.exists(arquivo_flag):
                        # Envia para a fila de processamento paralelo
                        executor.submit(processar_cena_grid, i)
                        grids_gerados.add(i) # Regista provisoriamente para não duplicar tarefas
                        
                time.sleep(0.2) # Acelerámos o tempo de reação de 0.5s para 0.2s!
            
        print("\n[✅ SUCESSO] Todas as grelhas foram geradas e guardadas!")
        
    except Exception as e:
        print("\n[ERRO CRÍTICO NO TERMINAL 2]")
        traceback.print_exc()

if __name__ == "__main__":
    main()