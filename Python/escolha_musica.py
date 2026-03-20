import os
import re
import random
from moviepy.editor import AudioFileClip, CompositeAudioClip, afx
from configuracoes import DEBUG_MODE

def processar_musicas(cenas_visuais, audio_locucao):
    """
    Agrupa blocos emocionais, lê o BPM matemático injetado pelo Python, 
    busca a música mais compatível na pasta e aplica nivelamento relativo de 15%.
    """
    duracao_total = audio_locucao.duration
    clipes = []
    
    # Verifica se existe pelo menos uma música em alguma subpasta
    if not any(f.endswith(('.mp3', '.wav')) for r, d, files in os.walk("musicas") for f in files):
        if DEBUG_MODE: print("      [Aviso] Nenhuma música encontrada nas pastas. O vídeo ficará sem trilha sonora.")
        return None

    if DEBUG_MODE: print("      [DEBUG] Extraindo pico de amplitude da narração para nivelar o áudio...")
    try: pico_narra = audio_locucao.max_volume()
    except: pico_narra = 1.0

    # 1. Agrupar cenas consecutivas com o mesmo humor e calcular o BPM alvo
    blocos_musicais = []
    bloco_atual = None
    mapa_climas = {
        'raiva': 'Raiva', 'animado': 'Animado', 'calmo': 'Calmo',
        'sombrio': 'Sombrio', 'dram': 'Dramático', 'vibrante': 'Vibrante',
        'alegre': 'Alegre', 'inspirador': 'Inspirador', 'romant': 'Romântico',
        'românt': 'Romântico', 'melanc': 'Melancólico'
    }

    for cena in cenas_visuais:
        raw_mood = cena.get('bgm_mood', 'Calmo').lower()
        mood_limpo = "Calmo"
        bpm_alvo = cena.get('bgm_bpm', 120) 
        
        for chave, valor_oficial in mapa_climas.items():
            if chave in raw_mood:
                mood_limpo = valor_oficial
                break

        if bloco_atual is None:
            bloco_atual = {"mood": mood_limpo, "bpm_alvo": bpm_alvo, "inicio": cena['inicio'], "fim": cena['fim']}
        elif bloco_atual["mood"] == mood_limpo:
            bloco_atual["fim"] = cena['fim']
            # Mantém uma média do BPM exigido durante o bloco
            bloco_atual["bpm_alvo"] = (bloco_atual["bpm_alvo"] + bpm_alvo) // 2 
        else:
            blocos_musicais.append(bloco_atual)
            bloco_atual = {"mood": mood_limpo, "bpm_alvo": bpm_alvo, "inicio": cena['inicio'], "fim": cena['fim']}
            
    if bloco_atual: blocos_musicais.append(bloco_atual)

    # 2. Mixagem com Pareamento Inteligente de BPM e Cálculo de 15%
    for i, bloco in enumerate(blocos_musicais):
        pasta = f"musicas/{bloco['mood']}"
        arqs = [f for f in os.listdir(pasta) if f.endswith(('.mp3', '.wav'))] if os.path.exists(pasta) else []
        
        target_bpm = bloco['bpm_alvo']
        melhor_arq = None
        menor_diferenca = 999
        
        if arqs:
            for f in arqs:
                # Procura por "130bpm" ou "_130_" no nome do arquivo
                match = re.search(r'(?i)(\d{2,3})\s*bpm', f) or re.search(r'_(\d{2,3})\.', f)
                if match:
                    bpm_arquivo = int(match.group(1))
                    if 60 <= bpm_arquivo <= 250: 
                        diff = abs(bpm_arquivo - target_bpm)
                        if diff < menor_diferenca:
                            menor_diferenca = diff
                            melhor_arq = f
            
            if melhor_arq is None: melhor_arq = random.choice(arqs)
            arq = os.path.join(pasta, melhor_arq)
            if DEBUG_MODE: print(f"      [DEBUG] Bloco {bloco['mood']} pediu {target_bpm} BPM. Escolhido: {melhor_arq}")
        else:
            todas = [os.path.join(r, m) for r, d, f in os.walk("musicas") for m in f if m.endswith(('.mp3', '.wav'))]
            if todas: arq = random.choice(todas)
            else: continue
            
        margem_crossfade = 1.5 if i < len(blocos_musicais) - 1 else 0
        dur_bloco = (bloco['fim'] - bloco['inicio']) + margem_crossfade
        
        try:
            m_clip = AudioFileClip(arq)
            
            # Cálculo matemático: 15% do pico de volume da narração
            try:
                pico_bgm = m_clip.max_volume()
                if pico_bgm == 0: pico_bgm = 1.0
            except: pico_bgm = 1.0
            fator_volume = (pico_narra * 0.15) / pico_bgm
            
            if m_clip.duration < dur_bloco:
                m_clip = afx.audio_loop(m_clip, duration=dur_bloco)
            else:
                m_clip = m_clip.subclip(0, dur_bloco)

            m_clip = m_clip.fx(afx.volumex, fator_volume)
            if i > 0: m_clip = m_clip.fx(afx.audio_fadein, 1.5)
            if margem_crossfade > 0: m_clip = m_clip.fx(afx.audio_fadeout, 1.5)
            
            m_clip = m_clip.set_start(bloco['inicio'])
            clipes.append(m_clip)
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] Erro ao processar áudio {arq}: {e}")
            continue
            
    return CompositeAudioClip(clipes).set_duration(duracao_total) if clipes else None