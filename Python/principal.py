import os
import json
import time
import gc
import concurrent.futures
import sys
import requests
import platform
from moviepy.editor import AudioFileClip, CompositeAudioClip

import configuracoes
from configuracoes import *
from agentes_texto import transcrever_e_direcionar
from extrator_imagens import pre_buscar_urls, baixar_candidatos
from agente_visao import escolher_imagem_ia_base64, gerar_grid_3x3_base64, analisar_ponto_focal, descarregar_modelo
from escolha_musica import processar_musicas

# --- DETECÇÃO GLOBAL DE SISTEMA OPERACIONAL ---
SISTEMA = platform.system()

# --- BLINDAGEM DE DIRETÓRIOS E FUNÇÕES AUXILIARES MANTIDAS ---
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_RAIZ_PROJETO = os.path.dirname(DIRETORIO_ATUAL)
PASTA_SAIDA_PROJETO = os.path.join(DIRETORIO_RAIZ_PROJETO, "Saída")

ARQUIVO_ESTADO = os.path.join(DIRETORIO_ATUAL, "estado_projeto.json")
VIDEO_FINAL = os.path.join(PASTA_SAIDA_PROJETO, "video_pronto.mp4")
TRILHA_FINAL = os.path.join(PASTA_SAIDA_PROJETO, "trilha_sonora_bgm.mp3")

def limpar_pastas_imagens():
    # Limpa as imagens normais e os upscales ao começar do zero
    pastas_para_limpar = ['temp_imagens', 'imagens_finais', os.path.join('imagens_finais', 'upscale')]
    for pasta in pastas_para_limpar:
        if os.path.exists(pasta):
            for f in os.listdir(pasta):
                caminho_arquivo = os.path.join(pasta, f)
                if os.path.isfile(caminho_arquivo):
                    try: os.remove(caminho_arquivo)
                    except: pass

def main():
    print("===================================================")
    print("      MINDKUT BETA - EDIÇÃO IMPERIAL v1.26.4.2     ")
    print("===================================================")
    print(f"[AMBIENTE] Sistema detectado: {SISTEMA}")

    # A ESCOLHA DO MODO AGORA É A PRIMEIRA COISA!
    print("\n===================================================")
    print("   SISTEMA DE INICIALIZAÇÃO (MINDKUT)              ")
    print("===================================================")
    print("[1] Começar do ZERO (Gerar novo projeto com IA)")
    print("[2] Abrir Editor Vazio (Para Importar Projeto .mindkut)")
    escolha = input("Digite 1 (Começar do ZERO) ou 2 (Reaproveitar): ").strip()

    if escolha == '1':
        print("\n===================================================")
        print("            DEFINIÇÃO DE FORMATO DO PROJETO        ")
        print("===================================================")
        print("1 - Vídeo Horizontal (16:9) - Padrão YouTube")
        print("2 - Short Vertical (9:16) - Shorts/TikTok/Reels")
        escolha_formato = input("Escolha o formato (1 ou 2): ").strip()

        if escolha_formato == '2':
            print(" -> Formato ajustado para SHORT VERTICAL (1080x1920).")
            configuracoes.TIPO_DE_VIDEO = '9:16'
            configuracoes.RESOLUCAO = (1080, 1920)
        else:
            print(" -> Formato ajustado para VÍDEO HORIZONTAL (1920x1080).")
            configuracoes.TIPO_DE_VIDEO = '16:9'
            configuracoes.RESOLUCAO = (1920, 1080)

        print("\n===================================================")
        print("               RITMO DO VÍDEO (PACING)             ")
        print("===================================================")
        print("Defina a duração média de cada imagem na tela.")
        print("Recomendado: 3.0 (YouTube normal) | 1.5 (Shorts frenéticos)")
        input_ritmo = input("Digite os segundos (ex: 2.5) ou ENTER para padrão: ").strip()
        
        try:
            if input_ritmo:
                tempo_alvo = float(input_ritmo.replace(',', '.'))
                if tempo_alvo < 0.5: tempo_alvo = 0.5
            else:
                tempo_alvo = 3.0
        except ValueError:
            print(" -> Valor inválido detectado. Assumindo padrão de 3.0 segundos.")
            tempo_alvo = 3.0
            
        print(f" -> Ritmo matematicamente ajustado para {tempo_alvo}s por cena.")
        print("\n[STATUS] Modo 1 acionado: A limpar terreno...")
        
        limpar_pastas_imagens()
        if os.path.exists(ARQUIVO_ESTADO): os.remove(ARQUIVO_ESTADO)
        if os.path.exists(VIDEO_FINAL):
            try: os.remove(VIDEO_FINAL)
            except PermissionError:
                print("\n[ERRO CRÍTICO] O arquivo 'video_pronto.mp4' está ABERTO em outro programa!")
                return

        cenas_visuais = transcrever_e_direcionar(ARQUIVO_AUDIO, tempo_alvo=tempo_alvo)
        with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
            json.dump({"cenas": cenas_visuais}, f, ensure_ascii=False, indent=4)
            
        audio_locucao = AudioFileClip(ARQUIVO_AUDIO)
        total_cenas = len(cenas_visuais)

        nucleos = os.cpu_count() or 2
        if SISTEMA == "Linux":
            workers_radar = max(2, nucleos * 2)
            cenas_simultaneas = max(2, nucleos) 
            workers_curadoria = 1
        else:
            workers_radar = 10
            cenas_simultaneas = 10 
            workers_curadoria = 8

        print(f"\n[2.0/5] Radar de Links (Nuvem): Mapeando internet para {total_cenas} cenas com {workers_radar} workers...")
        def worker_radar(i, cena):
            cena['urls_pre_carregadas'] = pre_buscar_urls(cena.get('query', 'anime visual'), i)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_radar) as executor:
            futuros = [executor.submit(worker_radar, i, c) for i, c in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass
        
        print(f"\n[2.1/5] Mineração Paralela e Geração de Grids -> {cenas_simultaneas} workers trabalhando SIMULTANEAMENTE...")
        def processar_cena_mineracao(i, cena):
            baixar_candidatos(cena.get('query', 'anime visual'), i, cena.get('urls_pre_carregadas', []))

        with concurrent.futures.ThreadPoolExecutor(max_workers=cenas_simultaneas) as executor:
            futuros = [executor.submit(processar_cena_mineracao, i, cena) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass 

        print(f"\n[2.2/5] Curadoria de Imagens (LLM Local em Rajada com {workers_curadoria} workers)...")
        for i, cena in enumerate(cenas_visuais):
            caminho_txt = f"temp_imagens/cena_{i:03d}_grid.txt"
            if os.path.exists(caminho_txt):
                with open(caminho_txt, 'r', encoding='utf-8') as f:
                    cena['grid_b64'] = f.read()
                
        def orquestrar_curadoria(cena, i):
            if cena.get('grid_b64'):
                vencedor = escolher_imagem_ia_base64(cena.get('query', 'anime scene'), cena['grid_b64'], id_cena=f"{i:03d}")
                cena['candidato_vencedor'] = vencedor
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_curadoria) as executor:
            futuros_ia = [executor.submit(orquestrar_curadoria, cena, i) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros_ia): pass

        descarregar_modelo()

        print("\n[2.3/5] Limpeza de Lixo e Consolidação Visual...")
        for i, cena in enumerate(cenas_visuais):
            vencedor = cena.get('candidato_vencedor', 1)
            img_final = f"imagens_finais/cena_{i:03d}.jpg"
            img_escolhida = f"temp_imagens/cena_{i:03d}_cand_{vencedor}.jpg"
            if os.path.exists(img_escolhida): os.rename(img_escolhida, img_final)
            for j in range(1, 6):
                cand = f"temp_imagens/cena_{i:03d}_cand_{j}.jpg"
                if os.path.exists(cand): os.remove(cand)
            flag = f"temp_imagens/cena_{i:03d}_ok.flag"
            if os.path.exists(flag): os.remove(flag)
            txt = f"temp_imagens/cena_{i:03d}_grid.txt"
            if os.path.exists(txt): os.remove(txt)
            if 'grid_b64' in cena: del cena['grid_b64']
            if 'candidato_vencedor' in cena: del cena['candidato_vencedor']
            if 'urls_pre_carregadas' in cena: del cena['urls_pre_carregadas']
            
        gc.collect() 

        print("\n[2.5/5] Analisando Enquadramento Inteligente (Visão Sequencial)...")
        def orquestrar_foco(cena, i):
            img_final = f"imagens_finais/cena_{i:03d}.jpg"
            if os.path.exists(img_final):
                img_b64_com_grid = gerar_grid_3x3_base64(img_final)
                if img_b64_com_grid:
                    cena['quadros_foco'] = analisar_ponto_focal(img_b64_com_grid, cena.get('texto', ''), cena.get('query', ''), id_cena=f"{i:03d}")
                else:
                    cena['quadros_foco'] = [5]
            else:
                cena['quadros_foco'] = [5]

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futuros = [executor.submit(orquestrar_foco, cena, i) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass

        descarregar_modelo()
        
        print("\n[3/5] Mapeando Trilha Sonora Multitrack...")
        faixas_musicais = processar_musicas(cenas_visuais, audio_locucao.duration)
        
        with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
            json.dump({"cenas": cenas_visuais, "faixas_musicais": faixas_musicais}, f, ensure_ascii=False, indent=4)

        AUDIO_TEMP_MESTRE = "temp_audio_mestre.wav"
        audio_locucao.write_audiofile(AUDIO_TEMP_MESTRE, fps=44100, logger=None)
        duracao_final_audio = audio_locucao.duration
        audio_locucao.close()
        
    elif escolha == '2':
        # ==========================================
        # MODO DE IMPORTAÇÃO (CAIXA VAZIA)
        # ==========================================
        print("\n[STATUS] Modo 2 acionado: Abrindo Editor Vazio para Importação...")
        limpar_pastas_imagens()
        
        # Cria a "Folha em Branco" para a interface não crashar
        projeto_vazio = {
            "duracao": 5.0,
            "formato": "16:9",
            "resolucao": [1920, 1080],
            "cenas": [],
            "faixas_musicais": [],
            "volumes_camadas": {"a1": 1.0, "a2": 1.0, "v1": 1.0},
            "volume_locucao": 1.0
        }
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(projeto_vazio, f, indent=4)
            
        cenas_visuais = []
        faixas_musicais = []
        duracao_final_audio = 5.0
        AUDIO_TEMP_MESTRE = "audio_vazio.wav"  # Arquivo fantasma, o front-end ignora falhas de áudio
    else:
        print("[ERRO] Escolha inválida. O sistema será encerrado.")
        return

    # PONTO DE CONVERGÊNCIA: Inicia o servidor web independentemente da escolha
    print("\n[4/5] Levantando Servidor Web e Interface de Edição...")
    import servidor_web
    servidor_web.iniciar_servidor(
        cenas_visuais=cenas_visuais,
        faixas_musicais=faixas_musicais,
        duracao_total=duracao_final_audio,
        arquivo_audio_final=AUDIO_TEMP_MESTRE,
        arquivo_saida=VIDEO_FINAL
    )
    
    if AUDIO_TEMP_MESTRE and os.path.exists(AUDIO_TEMP_MESTRE):
        os.remove(AUDIO_TEMP_MESTRE)

    print("\n=== MAESTRO FINALIZADO COM SUCESSO ===")

if __name__ == "__main__":
    main()
