import os
import random
import re
import numpy as np
from PIL import Image
from moviepy.editor import AudioFileClip, VideoClip, CompositeAudioClip, afx
from configuracoes import *

def aplicar_animacao_inteligente(caminho_img, duracao, quadros_foco):
    img_pil = Image.open(caminho_img).convert('RGB')
    w_orig, h_orig = img_pil.size
    target_w, target_h = RESOLUCAO
    
    if DEBUG_MODE: print(f"      [DEBUG] [MoviePy] A preparar clipe: {os.path.basename(caminho_img)} | Duração: {duracao:.2f}s | Foco IA: {quadros_foco}")
    if DEBUG_MODE: print(f"      [DEBUG] [MoviePy] Resolução Original: {w_orig}x{h_orig} -> Alvo: {target_w}x{target_h}")
    
    if not quadros_foco or not isinstance(quadros_foco, list): quadros_foco = [5]
    
    cx_total, cy_total = 0, 0
    for q in quadros_foco:
        if not isinstance(q, int) or q < 1 or q > 9: q = 5
        row, col = (q - 1) // 3, (q - 1) % 3
        cx_total += (col * (1/3)) + (1/6)
        cy_total += (row * (1/3)) + (1/6)
        
    foco_pct_x = cx_total / len(quadros_foco)
    foco_pct_y = cy_total / len(quadros_foco)
    maioria_grid = len(quadros_foco) >= 5
    
    foco_abs_x = w_orig * foco_pct_x
    foco_abs_y = h_orig * foco_pct_y
    
    target_aspect = target_w / target_h
    img_aspect = w_orig / h_orig
    
    if img_aspect > target_aspect:
        max_h = h_orig
        max_w = int(h_orig * target_aspect)
    else:
        max_w = w_orig
        max_h = int(w_orig / target_aspect)
        
    zoom_factor = 0.75
    min_w, min_h = int(max_w * zoom_factor), int(max_h * zoom_factor)
    
    def clamp_window(cw, ch, cx, cy):
        left = max(0, min(cx - cw / 2, w_orig - cw))
        top = max(0, min(cy - ch / 2, h_orig - ch))
        return (left, top, left + cw, top + ch)
        
    animacao = random.choice(["zoom_in", "zoom_out", "pan"]) if not maioria_grid else "pan_longo"
    if DEBUG_MODE: print(f"      [DEBUG] [MoviePy] Animação Matemática escolhida: {animacao.upper()}")
    
    if animacao == "zoom_in":
        start_box = clamp_window(max_w, max_h, foco_abs_x, foco_abs_y)
        end_box = clamp_window(min_w, min_h, foco_abs_x, foco_abs_y)
    elif animacao == "zoom_out":
        start_box = clamp_window(min_w, min_h, foco_abs_x, foco_abs_y)
        end_box = clamp_window(max_w, max_h, foco_abs_x, foco_abs_y)
    elif animacao == "pan":
        cw, ch = min_w, min_h
        if img_aspect > target_aspect: 
            offset = w_orig * 0.15
            sx, ex = foco_abs_x - offset, foco_abs_x + offset
            if random.choice([True, False]): sx, ex = ex, sx
            start_box = clamp_window(cw, ch, sx, foco_abs_y)
            end_box = clamp_window(cw, ch, ex, foco_abs_y)
        else: 
            offset = h_orig * 0.15
            sy, ey = foco_abs_y - offset, foco_abs_y + offset
            if random.choice([True, False]): sy, ey = ey, sy
            start_box = clamp_window(cw, ch, foco_abs_x, sy)
            end_box = clamp_window(cw, ch, foco_abs_x, ey)
    else: 
        cw, ch = max_w, max_h
        if img_aspect > target_aspect:
            sx, ex = (cw / 2, w_orig - (cw / 2)) if random.choice([True, False]) else (w_orig - (cw / 2), cw / 2)
            start_box = clamp_window(cw, ch, sx, foco_abs_y)
            end_box = clamp_window(cw, ch, ex, foco_abs_y)
        else:
            sy, ey = (ch / 2, h_orig - (ch / 2)) if random.choice([True, False]) else (h_orig - (ch / 2), ch / 2)
            start_box = clamp_window(cw, ch, foco_abs_x, sy)
            end_box = clamp_window(cw, ch, foco_abs_x, ey)
            
    def make_frame(t):
        progress = t / duracao
        cur_left = start_box[0] + (end_box[0] - start_box[0]) * progress
        cur_top = start_box[1] + (end_box[1] - start_box[1]) * progress
        cur_right = start_box[2] + (end_box[2] - start_box[2]) * progress
        cur_bottom = start_box[3] + (end_box[3] - start_box[3]) * progress
        
        cropped = img_pil.crop((cur_left, cur_top, cur_right, cur_bottom))
        # OTIMIZAÇÃO: BILINEAR é cerca de 40% mais rápido em movimento sem perda humana de qualidade!
        resized = cropped.resize((target_w, target_h), Image.Resampling.BILINEAR)
        
        return np.array(resized)

    return VideoClip(make_frame, duration=duracao)
    
def processar_musicas(cenas_visuais, audio_locucao):
    duracao_total = audio_locucao.duration
    clipes = []
    if DEBUG_MODE: print("\n      [DEBUG] [Mixagem] A iniciar análise dinâmica de áudio...")
    
    if not any(f.endswith(('.mp3', '.wav')) for r, d, files in os.walk("musicas") for f in files):
        if DEBUG_MODE: print("      [DEBUG] [Mixagem] Nenhuma música encontrada nas pastas.")
        return None

    try: pico_narra = audio_locucao.max_volume()
    except: pico_narra = 1.0
    if DEBUG_MODE: print(f"      [DEBUG] [Mixagem] Pico máximo da narração detetado: {pico_narra:.4f} dB")

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
            bloco_atual["bpm_alvo"] = (bloco_atual["bpm_alvo"] + bpm_alvo) // 2 
        else:
            blocos_musicais.append(bloco_atual)
            bloco_atual = {"mood": mood_limpo, "bpm_alvo": bpm_alvo, "inicio": cena['inicio'], "fim": cena['fim']}
            
    if bloco_atual: blocos_musicais.append(bloco_atual)

    for i, bloco in enumerate(blocos_musicais):
        pasta = f"musicas/{bloco['mood']}"
        arqs = [f for f in os.listdir(pasta) if f.endswith(('.mp3', '.wav'))] if os.path.exists(pasta) else []
        
        target_bpm = bloco['bpm_alvo']
        melhor_arq = None
        menor_diferenca = 999
        
        if arqs:
            for f in arqs:
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
        else:
            todas = [os.path.join(r, m) for r, d, f in os.walk("musicas") for m in f if m.endswith(('.mp3', '.wav'))]
            if todas: arq = random.choice(todas)
            else: continue
            
        margem_crossfade = 1.5 if i < len(blocos_musicais) - 1 else 0
        dur_bloco = (bloco['fim'] - bloco['inicio']) + margem_crossfade
        
        if DEBUG_MODE: print(f"      [DEBUG] [Mixagem] Bloco {i+1}: Mood '{bloco['mood']}' | Exige {target_bpm} BPM. Escolhido: {os.path.basename(arq)}")
        
        try:
            m_clip = AudioFileClip(arq)
            
            try:
                pico_bgm = m_clip.max_volume()
                if pico_bgm == 0: pico_bgm = 1.0
            except: pico_bgm = 1.0
            fator_volume = (pico_narra * 0.15) / pico_bgm
            
            if DEBUG_MODE: print(f"      [DEBUG] [Mixagem] A regular BGM para {fator_volume*100:.1f}% do original para respeitar a Locução.")
            
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
            if DEBUG_MODE: print(f"      [DEBUG] [ERRO Mixagem] Falha ao processar {arq}: {e}")
            continue
            
    return CompositeAudioClip(clipes).set_duration(duracao_total) if clipes else None