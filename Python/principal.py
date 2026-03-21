import os
import json
import time
import gc
import concurrent.futures
import sys
import requests
import subprocess
from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip

from configuracoes import *
from agentes_texto import transcrever_e_direcionar
from extrator_imagens import pre_buscar_urls, baixar_candidatos
from agente_visao import escolher_imagem_ia_base64, gerar_grid_3x3_base64, analisar_ponto_focal
from motor_video import aplicar_animacao_inteligente
from escolha_musica import processar_musicas

# --- BLINDAGEM DE DIRETÓRIOS ---
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_RAIZ_PROJETO = os.path.dirname(DIRETORIO_ATUAL)
if not os.path.exists(os.path.join(DIRETORIO_RAIZ_PROJETO, "Entrada")):
    DIRETORIO_RAIZ_PROJETO = DIRETORIO_ATUAL

PASTA_SAIDA_PROJETO = os.path.join(DIRETORIO_RAIZ_PROJETO, "Saída")
ARQUIVO_ESTADO = os.path.join(DIRETORIO_ATUAL, "estado_projeto.json")
VIDEO_FINAL = os.path.join(PASTA_SAIDA_PROJETO, "video_pronto.mp4")
TRILHA_FINAL = os.path.join(PASTA_SAIDA_PROJETO, "trilha_sonora_bgm.mp3")

def descarregar_modelo_ollama(nome_modelo):
    if DEBUG_MODE: print(f"      [DEBUG] Descarregando modelo '{nome_modelo}' da VRAM/RAM...")
    try: requests.post("http://127.0.0.1:11434/api/chat", json={"model": nome_modelo, "keep_alive": 0}, timeout=5)
    except: pass

def limpar_pastas_imagens():
    for pasta in ['temp_imagens', 'imagens_finais']:
        caminho_completo = os.path.join(DIRETORIO_RAIZ_PROJETO, pasta)
        if os.path.exists(caminho_completo):
            for f in os.listdir(caminho_completo):
                try: os.remove(os.path.join(caminho_completo, f))
                except: pass

def garantir_modelos_baixados():
    print("\n[SISTEMA] Mapeando hardware e verificando modelos locais...")
    vram, ram = obter_recursos_sistema()
    mod_jun = escolher_modelo_junior(vram, ram)
    mod_sen = escolher_modelo_senior(vram, ram)
    mod_vis = "qwen3-vl:8b" 
    
    modelos_necessarios = list(set([mod_jun, mod_sen, mod_vis]))
    
    print(f"[STATUS] Modelos exigidos pela sua máquina (VRAM Livre: {vram:.1f}GB):")
    for m in modelos_necessarios: print(f" -> {m}")
        
    for modelo in modelos_necessarios:
        try:
            subprocess.run(["ollama", "pull", modelo], check=True, stdout=subprocess.DEVNULL)
        except Exception as e:
            pass
            
    print("[SISTEMA] Todos os modelos estão cacheados e prontos para uso na GPU!\n")

def main():
    print("===================================================")
    print("      MAESTRO V4.0 (ORQUESTRADOR HÍBRIDO)          ")
    print("===================================================")

    garantir_modelos_baixados()

    print("\n===================================================")
    print("   SISTEMA DE RECUPERAÇÃO DE ESTADO (CAIXA PRETA)")
    print("===================================================")
    escolha = input("Digite 1 (Começar do ZERO) ou 2 (Reaproveitar): ").strip()

    if escolha == '1':
        print("\n[STATUS] Modo 1 acionado: A limpar terreno...")
        limpar_pastas_imagens()
        if os.path.exists(ARQUIVO_ESTADO): os.remove(ARQUIVO_ESTADO)
        
        try:
            if os.path.exists(VIDEO_FINAL): os.remove(VIDEO_FINAL)
        except PermissionError:
            print("\n[ERRO CRÍTICO] O arquivo 'video_pronto.mp4' está ABERTO em outro programa!")
            return

        cenas_visuais = transcrever_e_direcionar(ARQUIVO_AUDIO)
        with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
            json.dump({"cenas": cenas_visuais}, f, ensure_ascii=False, indent=4)
    else:
        if not os.path.exists(ARQUIVO_ESTADO): return
        with open(ARQUIVO_ESTADO, 'r', encoding='utf-8') as f:
            cenas_visuais = json.load(f)['cenas']

    audio_locucao = AudioFileClip(ARQUIVO_AUDIO)
    clipes_de_video = []
    total_cenas = len(cenas_visuais)

    if escolha == '1':
        print(f"\n[2.0/5] Radar de Links (Nuvem): Mapeando internet para {total_cenas} cenas...")
        def worker_radar(i, cena):
            cena['urls_pre_carregadas'] = pre_buscar_urls(cena.get('query', 'Naruto anime'), i)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futuros = [executor.submit(worker_radar, i, c) for i, c in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass
                
        cenas_simultaneas = 10 
        
        print(f"\n[2.1/5] Mineração Paralela -> {cenas_simultaneas} workers baixando imagens e montando grids SIMULTANEAMENTE...")
        def processar_cena_mineracao(i, cena):
            baixar_candidatos(cena.get('query', 'Naruto anime'), i, cena.get('urls_pre_carregadas', []))

        # A execução só passa para a Fase 2.2 quando TODOS os workers finalizarem!
        with concurrent.futures.ThreadPoolExecutor(max_workers=cenas_simultaneas) as executor:
            futuros = [executor.submit(processar_cena_mineracao, i, cena) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass 

    print("\n[2.2/5] Curadoria de Imagens (LLM Local em Rajada)...")
    for i, cena in enumerate(cenas_visuais):
        caminho_txt = os.path.join(DIRETORIO_RAIZ_PROJETO, f"temp_imagens/cena_{i:03d}_grid.txt")
        if os.path.exists(caminho_txt):
            with open(caminho_txt, 'r', encoding='utf-8') as f:
                cena['grid_b64'] = f.read()
            
    def orquestrar_curadoria(cena):
        if cena.get('grid_b64'):
            vencedor = escolher_imagem_ia_base64(cena.get('query', 'anime scene'), cena['grid_b64'])
            cena['candidato_vencedor'] = vencedor
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futuros_ia = [executor.submit(orquestrar_curadoria, cena) for cena in cenas_visuais]
        for _ in concurrent.futures.as_completed(futuros_ia): pass

    print("\n[2.3/5] Limpeza de Lixo e Consolidação Visual...")
    for i, cena in enumerate(cenas_visuais):
        vencedor = cena.get('candidato_vencedor', 1)
        img_final = os.path.join(DIRETORIO_RAIZ_PROJETO, f"imagens_finais/cena_{i:03d}.jpg")
        img_escolhida = os.path.join(DIRETORIO_RAIZ_PROJETO, f"temp_imagens/cena_{i:03d}_cand_{vencedor}.jpg")
        
        if os.path.exists(img_escolhida): os.rename(img_escolhida, img_final)
        
        for j in range(1, 6):
            cand = os.path.join(DIRETORIO_RAIZ_PROJETO, f"temp_imagens/cena_{i:03d}_cand_{j}.jpg")
            if os.path.exists(cand): os.remove(cand)
        
        flag = os.path.join(DIRETORIO_RAIZ_PROJETO, f"temp_imagens/cena_{i:03d}_ok.flag")
        if os.path.exists(flag): os.remove(flag)
        txt = os.path.join(DIRETORIO_RAIZ_PROJETO, f"temp_imagens/cena_{i:03d}_grid.txt")
        if os.path.exists(txt): os.remove(txt)
            
        if 'grid_b64' in cena: del cena['grid_b64']
        if 'candidato_vencedor' in cena: del cena['candidato_vencedor']
        if 'urls_pre_carregadas' in cena: del cena['urls_pre_carregadas']
        
    gc.collect() 

    descarregar_modelo_ollama("qwen3-vl:8b") 
    print("\n[2.5/5] Analisando Enquadramento Inteligente (Visão Paralela)...")
    
    def orquestrar_foco(cena, i):
        img_final = os.path.join(DIRETORIO_RAIZ_PROJETO, f"imagens_finais/cena_{i:03d}.jpg")
        if os.path.exists(img_final):
            img_b64_com_grid = gerar_grid_3x3_base64(img_final)
            if img_b64_com_grid:
                cena['quadros_foco'] = analisar_ponto_focal(img_b64_com_grid, cena.get('texto', ''), cena.get('query', ''))
            else:
                cena['quadros_foco'] = [5]
        else:
            cena['quadros_foco'] = [5]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futuros_foco = [executor.submit(orquestrar_foco, cena, i) for i, cena in enumerate(cenas_visuais)]
        for _ in concurrent.futures.as_completed(futuros_foco): pass

    with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
        json.dump({"cenas": cenas_visuais}, f, ensure_ascii=False, indent=4)

    descarregar_modelo_ollama("qwen3-vl:8b") 
    print("\n[3/5] Montando a Timeline (Animação Inteligente Absoluta)...")
    for i, cena in enumerate(cenas_visuais):
        img_final = os.path.join(DIRETORIO_RAIZ_PROJETO, f"imagens_finais/cena_{i:03d}.jpg")
        if os.path.exists(img_final):
            inicio_cena = cena.get('inicio', 0.0)
            duracao = cena.get('fim', 0.0) - inicio_cena
            if duracao <= 0: duracao = 3.0
            clip = aplicar_animacao_inteligente(img_final, duracao, cena.get('quadros_foco', [5]))
            clipes_de_video.append(clip.set_start(inicio_cena))

    print("\n[4/5] Renderizando Áudio e Trilha Sonora...")
    trilha = processar_musicas(cenas_visuais, audio_locucao)
    if trilha: trilha.write_audiofile(TRILHA_FINAL, fps=44100, logger=None)
    audio_final = CompositeAudioClip([audio_locucao, trilha]) if trilha else audio_locucao

    print(f"\n[5/5] Renderizando Vídeo Final para a pasta Saída...")
    if clipes_de_video:
        video_completo = CompositeVideoClip(clipes_de_video, size=RESOLUCAO).set_audio(audio_final).set_duration(audio_locucao.duration)
        try: video_completo.write_videofile(VIDEO_FINAL, fps=24, codec="h264_nvenc", audio_codec="aac", bitrate="15000k", threads=4, ffmpeg_params=["-pix_fmt", "yuv420p", "-rc", "vbr", "-cq", "19", "-profile:v", "high"], logger="bar")
        except: video_completo.write_videofile(VIDEO_FINAL, fps=24, codec="libx264", audio_codec="aac", bitrate="15000k", threads=4, preset="superfast", ffmpeg_params=["-pix_fmt", "yuv420p"], logger="bar")
        video_completo.close()

    audio_locucao.close()
    if trilha: trilha.close()
    print("\n=== FINALIZADO ===")

if __name__ == "__main__":
    main()
