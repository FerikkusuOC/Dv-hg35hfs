import os
import platform
import json
import time
import gc
import concurrent.futures
import sys
import requests
import subprocess
from moviepy.editor import AudioFileClip, CompositeAudioClip

import configuracoes
from configuracoes import *
from agentes_texto import transcrever_e_direcionar
from extrator_imagens import pre_buscar_urls, baixar_candidatos
from agente_visao import escolher_imagem_ia_base64, gerar_grid_3x3_base64, analisar_ponto_focal, descarregar_modelo
from escolha_musica import processar_musicas

# Detecção de Ambiente
SISTEMA_WINDOWS = os.name == 'nt'
AMBIENTE_COLAB = "COLAB_GPU" in os.environ or "COLAB_RELEASE_TAG" in os.environ

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

def contar_grids_prontos():
    pasta = "temp_imagens" 
    if not os.path.exists(pasta): return 0
    return len([f for f in os.listdir(pasta) if f.endswith("_grid.txt")])

def main():
    print("===================================================")
    print("      MINDKUT BETA - EDIÇÃO IMPERIAL v1.26.4.2")
    print("===================================================")

    # Automação de Inputs via Variáveis de Ambiente (Colab Forms) ou Manual (Windows)
    if AMBIENTE_COLAB or not sys.stdin.isatty():
        escolha_formato = os.getenv("MINDKUT_FORMATO", "1").strip()
        input_ritmo = os.getenv("MINDKUT_RITMO", "3.0").strip()
        escolha = os.getenv("MINDKUT_RECUPERACAO", "1").strip()
        print(f"[COLAB MODE] Execução silenciosa. Formato: {escolha_formato}, Ritmo: {input_ritmo}, Modo: {escolha}")
    else:
        print("\n[1] Vídeo Horizontal (16:9) | [2] Short Vertical (9:16)")
        escolha_formato = input("Escolha o formato (1 ou 2): ").strip()
        input_ritmo = input("Digite o ritmo em segundos (ex: 2.5) ou ENTER para 3.0: ").strip()
        escolha = input("Digite 1 (Começar do ZERO) ou 2 (Reaproveitar projeto): ").strip()

    if escolha_formato == '2':
        configuracoes.TIPO_DE_VIDEO = '9:16'
        configuracoes.RESOLUCAO = (1080, 1920)
    else:
        configuracoes.TIPO_DE_VIDEO = '16:9'
        configuracoes.RESOLUCAO = (1920, 1080)

    try:
        tempo_alvo = float(input_ritmo.replace(',', '.')) if input_ritmo else 3.0
        if tempo_alvo < 0.5: tempo_alvo = 0.5
    except ValueError:
        tempo_alvo = 3.0

    if escolha == '1':
        print("\n[STATUS] Modo 1 acionado: A limpar terreno...")
        limpar_pastas_imagens()
        if os.path.exists(ARQUIVO_ESTADO): os.remove(ARQUIVO_ESTADO)
        try:
            if os.path.exists(VIDEO_FINAL): os.remove(VIDEO_FINAL)
        except PermissionError:
            print("\n[ERRO CRÍTICO] O arquivo final está ABERTO em outro programa!")
            return

        cenas_visuais = transcrever_e_direcionar(ARQUIVO_AUDIO, tempo_alvo=tempo_alvo)
        with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
            json.dump({"cenas": cenas_visuais}, f, ensure_ascii=False, indent=4)
            
        audio_locucao = AudioFileClip(ARQUIVO_AUDIO)
        total_cenas = len(cenas_visuais)

        print(f"\n[2.0/5] Radar de Links (Nuvem): Mapeando internet para {total_cenas} cenas...")
        def worker_radar(i, cena):
            cena['urls_pre_carregadas'] = pre_buscar_urls(cena.get('query', 'anime visual'), i)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futuros = [executor.submit(worker_radar, i, c) for i, c in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass
                
        # Controle de Workers Inteligente
        cenas_simultaneas = 10 if SISTEMA_WINDOWS else 4
        workers_visao = 8 if SISTEMA_WINDOWS else 2 

        print(f"\n[2.1/5] Mineração Paralela e Geração de Grids ({cenas_simultaneas} workers)...")
        def processar_cena_mineracao(i, cena):
            baixar_candidatos(cena.get('query', 'anime visual'), i, cena.get('urls_pre_carregadas', []))

        # A execução agora bloqueia e aguarda todos baixarem e montarem os grids sozinhos
        with concurrent.futures.ThreadPoolExecutor(max_workers=cenas_simultaneas) as executor:
            futuros = [executor.submit(processar_cena_mineracao, i, cena) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros): pass 

        print(" -> Sincronização concluída! Todos os grids gerados e salvos.")

        print("\n[2.2/5] Curadoria de Imagens (LLM Local em Rajada)...")
        for i, cena in enumerate(cenas_visuais):
            caminho_txt = f"temp_imagens/cena_{i:03d}_grid.txt"
            with open(caminho_txt, 'r', encoding='utf-8') as f:
                cena['grid_b64'] = f.read()
                
        def orquestrar_curadoria(cena, i):
            if cena.get('grid_b64'):
                vencedor = escolher_imagem_ia_base64(cena.get('query', 'anime scene'), cena['grid_b64'], id_cena=f"{i:03d}")
                cena['candidato_vencedor'] = vencedor
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_visao) as executor:
            futuros_ia = [executor.submit(orquestrar_curadoria, cena, i) for i, cena in enumerate(cenas_visuais)]
            for _ in concurrent.futures.as_completed(futuros_ia): pass

        # Limpando a Força-Tarefa da VRAM após a etapa
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
            
            # Não existe mais cena_XXX_ok.flag, apagamos apenas o txt do grid
            txt = f"temp_imagens/cena_{i:03d}_grid.txt"
            if os.path.exists(txt): os.remove(txt)
                
            if 'grid_b64' in cena: del cena['grid_b64']
            if 'candidato_vencedor' in cena: del cena['candidato_vencedor']
            if 'urls_pre_carregadas' in cena: del cena['urls_pre_carregadas']
            
        gc.collect() 

    else:
        # ==========================================
        # MODO 2: REAPROVEITAMENTO DIRETO
        # ==========================================
        print("\n[STATUS] Modo 2 acionado: Pulando mineração e recuperando projeto existente...")
        if not os.path.exists(ARQUIVO_ESTADO): 
            print("[ERRO] Arquivo de estado não encontrado!")
            return
        with open(ARQUIVO_ESTADO, 'r', encoding='utf-8') as f:
            cenas_visuais = json.load(f)['cenas']
        
        audio_locucao = AudioFileClip(ARQUIVO_AUDIO)
        total_cenas = len(cenas_visuais)

    # ==========================================
    # PONTO DE CONVERGÊNCIA (Ambos os modos passam por aqui)
    # ==========================================

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

    with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
        json.dump({"cenas": cenas_visuais}, f, ensure_ascii=False, indent=4)

    # Limpando a Força-Tarefa da VRAM
    descarregar_modelo()
    
    print("\n[3/5] Mapeando Trilha Sonora Multitrack...")
    faixas_musicais = processar_musicas(cenas_visuais, audio_locucao.duration)
    
    # Atualiza o JSON salvando a nova chave 'faixas_musicais'
    with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
        json.dump({
            "cenas": cenas_visuais, 
            "faixas_musicais": faixas_musicais
        }, f, ensure_ascii=False, indent=4)

    # Prepara APENAS A VOZ para ser o áudio mestre base
    AUDIO_TEMP_MESTRE = "temp_audio_mestre.wav"
    audio_locucao.write_audiofile(AUDIO_TEMP_MESTRE, fps=44100, logger=None)
    
    duracao_final_audio = audio_locucao.duration
    audio_locucao.close()

    # Inicia o Servidor Web imediatamente! A IA agora é controlada pela Interface.
    print("\n[4/5] Levantando Servidor Web e Interface de Edição...")
    import servidor_web
    servidor_web.iniciar_servidor(
        cenas_visuais=cenas_visuais,
        faixas_musicais=faixas_musicais,
        duracao_total=duracao_final_audio,
        arquivo_audio_final=AUDIO_TEMP_MESTRE,
        arquivo_saida=VIDEO_FINAL
    )
    
    # Limpeza do áudio temporário ao fechar o servidor
    if os.path.exists(AUDIO_TEMP_MESTRE):
        os.remove(AUDIO_TEMP_MESTRE)

    print("\n=== MAESTRO FINALIZADO COM SUCESSO ===")

if __name__ == "__main__":
    main()