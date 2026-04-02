import os
import re
import random
from configuracoes import DEBUG_MODE

def processar_musicas(cenas_visuais, duracao_total):
    """
    Agrupa blocos emocionais, lê o BPM matemático injetado pelo Python, 
    busca a música mais compatível na pasta e GERA O MAPA JSON PARA O FRONTEND.
    """
    faixas_json = []
    
    if not any(f.endswith(('.mp3', '.wav')) for r, d, files in os.walk("musicas") for f in files):
        if DEBUG_MODE: print("      [Aviso] Nenhuma música encontrada nas pastas. A timeline iniciará vazia.")
        return []

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
            bloco_atual["bpm_alvo"] = (bloco_atual["bpm_alvo"] + bpm_alvo) // 2 
        else:
            blocos_musicais.append(bloco_atual)
            bloco_atual = {"mood": mood_limpo, "bpm_alvo": bpm_alvo, "inicio": cena['inicio'], "fim": cena['fim']}
            
    if bloco_atual: blocos_musicais.append(bloco_atual)

    # 2. Pareamento Inteligente de BPM e Montagem do JSON
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
            arq_path = f"musicas/{bloco['mood']}/{melhor_arq}"
            if DEBUG_MODE: print(f"      [DEBUG] Bloco {bloco['mood']} pediu {target_bpm} BPM. Escolhido: {melhor_arq}")
        else:
            todas = [os.path.join(r, m).replace('\\', '/') for r, d, f in os.walk("musicas") for m in f if m.endswith(('.mp3', '.wav'))]
            if todas: 
                arq_path = random.choice(todas)
                melhor_arq = os.path.basename(arq_path)
            else: continue
            
        margem_crossfade = 1.5 if i < len(blocos_musicais) - 1 else 0
        dur_bloco = (bloco['fim'] - bloco['inicio']) + margem_crossfade

        # Monta a estrutura para o JavaScript
        faixas_json.append({
            "id": i,
            "arquivo": arq_path,
            "titulo": melhor_arq,
            "clima": bloco['mood'],
            "inicio": round(bloco['inicio'], 2),
            "fim": round(bloco['fim'] + margem_crossfade, 2),
            "volume": 0.15,
            "fade_in": 1.5 if i > 0 else 0.0,
            "fade_out": 1.5 if margem_crossfade > 0 else 0.0
        })
            
    return faixas_json