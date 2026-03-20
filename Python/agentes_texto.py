import os
import json
import time
import re
import requests
import gc
from google import genai
import ollama
from faster_whisper import WhisperModel
from configuracoes import *

def chamar_groq_texto(prompt, model_name, max_tentativas=3):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "top_p": 0.01
    }
    for tentativa in range(max_tentativas):
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 429:
            if DEBUG_MODE: print(f"      [Aviso Groq] Limite atingido. Pausando 30s antes de tentar de novo ({tentativa + 1}/{max_tentativas})...")
            time.sleep(30)
            continue
        res.raise_for_status()
        return res.json()['choices'][0]['message']['content']
    raise Exception(f"Falha no Groq para o modelo {model_name} após múltiplas tentativas.")

def gerar_texto_draft(prompt):
    for plataforma, modelo in FALLBACK_TEXTO:
        if DEBUG_MODE: print(f"      [DEBUG] [Texto Draft] Usando Nuvem: {modelo} via {plataforma.upper()}")
        try:
            if plataforma == "groq" and GROQ_KEY:
                return chamar_groq_texto(prompt, modelo)
        except Exception:
            continue
            
    vram, ram = obter_recursos_sistema()
    modelo_local = escolher_modelo_junior(vram, ram)
    if DEBUG_MODE: print(f"      [DEBUG] [Texto Draft Junior] Usando: Ollama Local ({modelo_local}) | VRAM Livre: {vram:.1f}GB")
    try:
        res = ollama.chat(model=modelo_local, messages=[{'role': 'user', 'content': prompt}], options={'temperature': 0.0, 'keep_alive': '5m'})
        
        if DEBUG_MODE: print(f"      [DEBUG] [Texto Draft Junior] Trabalho concluído. Descarregando {modelo_local} da VRAM.")
        descarregar_modelo_ollama(modelo_local) 
        gc.collect()
        
        return res['message']['content']
    except Exception as e:
        print(f"      [ERRO FATAL] O motor local de texto falhou: {e}")
        descarregar_modelo_ollama(modelo_local)
        return ""

def gerar_texto_revisor(prompt):
    global ESTADO_REVISOR
    
    if not ESTADO_REVISOR['gemini_esgotado'] and API_KEYS:
        usou_gemini = False
        for key_idx, key in enumerate(API_KEYS):
            for model_idx, modelo in enumerate(GEMINI_REVISOR_MODELS):
                if (key_idx, model_idx) in ESTADO_REVISOR['gemini_permanentes']: continue
                if (key_idx, model_idx) in ESTADO_REVISOR['gemini_cooldowns']:
                    if time.time() < ESTADO_REVISOR['gemini_cooldowns'][(key_idx, model_idx)]: continue 
                    else: del ESTADO_REVISOR['gemini_cooldowns'][(key_idx, model_idx)]

                if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] Usando: Gemini {modelo} (Chave {key_idx + 1}/{len(API_KEYS)})")
                try:
                    client = genai.Client(api_key=key)
                    res = client.models.generate_content(
                        model=modelo, 
                        contents=prompt, 
                        config={'temperature': 0.0, 'top_p': 0.01}
                    )
                    return res.text
                except Exception as e:
                    erro_str = str(e).lower()
                    if "perminute" in erro_str or "retry in" in erro_str or "429" in erro_str:
                        if "perday" in erro_str:
                            if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] Cota DIÁRIA do {modelo} esgotada. Descartando permanente.")
                            ESTADO_REVISOR['gemini_permanentes'].add((key_idx, model_idx))
                        else:
                            if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] Cota POR MINUTO do {modelo} atingida. Pausando modelo por 60s...")
                            ESTADO_REVISOR['gemini_cooldowns'][(key_idx, model_idx)] = time.time() + 60
                    else:
                        if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] Erro no {modelo}: {e}. Descartando permanente...")
                        ESTADO_REVISOR['gemini_permanentes'].add((key_idx, model_idx))
                    usou_gemini = True

        if len(ESTADO_REVISOR['gemini_permanentes']) >= len(API_KEYS) * len(GEMINI_REVISOR_MODELS):
            ESTADO_REVISOR['gemini_esgotado'] = True
            if DEBUG_MODE: print("      [DEBUG] [Texto Revisor] TODAS as APIs do Gemini esgotaram. Trocando permanentemente para Nuvem Secundária.")
        elif usou_gemini:
            if DEBUG_MODE: print("      [DEBUG] [Texto Revisor] Todos os Geminis estão em Cooldown. Acionando Nuvem Secundária temporariamente...")

    while ESTADO_REVISOR['fallback_idx'] < len(FALLBACK_TEXTO):
        plataforma, modelo = FALLBACK_TEXTO[ESTADO_REVISOR['fallback_idx']]
        if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] Usando Nuvem: {modelo} via {plataforma.upper()}")
        try:
            if plataforma == "groq" and GROQ_KEY: return chamar_groq_texto(prompt, modelo)
            else:
                ESTADO_REVISOR['fallback_idx'] += 1
                continue
        except Exception as e:
            if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor] {modelo} falhou: {e}. Indo para o próximo da fila...")
            ESTADO_REVISOR['fallback_idx'] += 1

    vram, ram = obter_recursos_sistema()
    modelo_local = escolher_modelo_senior(vram, ram)
    if DEBUG_MODE: print(f"      [DEBUG] [Texto Revisor Sênior] Usando: Ollama Local ({modelo_local}) | VRAM Livre: {vram:.1f}GB")
    try:
        res = ollama.chat(model=modelo_local, messages=[{'role': 'user', 'content': prompt}], options={'temperature': 0.0, 'keep_alive': '5m'})
        descarregar_modelo_ollama(modelo_local) 
        return res['message']['content']
    except Exception as e:
        print(f"      [ERRO FATAL] O motor local de revisão falhou: {e}")
        descarregar_modelo_ollama(modelo_local)
        return ""

def transcrever_audio_hibrido(audio_path):
    if GROQ_KEY:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}"}
        
        for modelo in WHISPER_MODELS:
            if DEBUG_MODE: print(f"      [DEBUG] [Whisper] A tentar Nuvem: {modelo}")
            sucesso_modelo = False
            
            for tentativa in range(3):
                try:
                    with open(audio_path, "rb") as file:
                        files = {"file": (os.path.basename(audio_path), file, "audio/mpeg")}
                        data = {"model": modelo, "response_format": "verbose_json", "timestamp_granularities[]": "word", "language": "pt"}
                        res = requests.post(url, headers=headers, files=files, data=data, timeout=60)
                        
                        if res.status_code == 429:
                            if DEBUG_MODE: print(f"      [DEBUG] [Whisper] Groq 429. Aguardando 60s ({tentativa + 1}/3)...")
                            time.sleep(60)
                            continue
                            
                        res.raise_for_status()
                        resultado = res.json()
                        if "words" in resultado:
                            if DEBUG_MODE: print(f"      [DEBUG] [Whisper] Sucesso com {modelo}!")
                            return [{"palavra": w["word"].strip(), "inicio": w["start"], "fim": w["end"]} for w in resultado["words"]]
                except Exception as e:
                    if DEBUG_MODE: print(f"      [DEBUG] [Whisper] Erro na tentativa {tentativa+1} ({e}).")
            
            if not sucesso_modelo:
                if DEBUG_MODE: print(f"      [DEBUG] [Whisper] Modelo {modelo} esgotado. Rebaixando...")
                
    if DEBUG_MODE: print("      [DEBUG] [Whisper] Nuvem falhou. A preparar motor Local (Faster-Whisper)...")
    vram, ram = obter_recursos_sistema()
    modelo_whisper = escolher_modelo_whisper(vram, ram)
    
    if DEBUG_MODE: print(f"      [DEBUG] [Whisper] Auto-Scale ativado: Modelo '{modelo_whisper}' (VRAM: {vram:.1f}GB)")
    
    device_type = "cuda" if vram >= 1.0 else "cpu"
    comp_type = "float16" if vram >= 1.0 else "int8"
    
    model = WhisperModel(modelo_whisper, device=device_type, compute_type=comp_type)
    vocabulario = "Naruto, Orochimaru, Konoha, Sasuke, Mitsuki, Boruto, Shin, Yamato, Uchiha, Hokage, Rasengan, Chidori, Sharingan, Light Novel"
    
    segments, _ = model.transcribe(audio_path, word_timestamps=True, initial_prompt=vocabulario, vad_filter=True)
    
    resultados = [{"palavra": w.word.strip(), "inicio": w.start, "fim": w.end} for s in segments for w in s.words]
    
    if DEBUG_MODE: print("      [DEBUG] [Whisper] Extração concluída. A expurgar modelo da GPU...")
    del model
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    except: pass
    
    return resultados

def obter_query_rapida(texto, historico_queries=None):
    if historico_queries is None: historico_queries = set()
    proibidas = ", ".join(historico_queries) if historico_queries else "None"
    prompt_base = f"""Read this short text: '{texto}'.
    TASK: Generate an image search query.
    RULES:
    1. LANGUAGE: STRICTLY ENGLISH. Zero tolerance for Portuguese.
    2. TRANSLATE: You MUST translate Portuguese terms to English.
    3. FORMAT: Max 3 words. Physical and visual only.
    4. NO quotes, no extra text.
    5. FORBIDDEN QUERIES (DO NOT REPEAT ANY OF THESE): [{proibidas}]
    6. REAL-WORLD SEARCHABILITY: Make it a generic Google Images search term. DO NOT use AI-generation modifiers (no 'cinematic', '4k', 'dramatic lighting'). Keep it generic and findable.
    
    Query:"""
    
    prompt = prompt_base
    for tentativa in range(3):
        if DEBUG_MODE and tentativa > 0: print(f"      [DEBUG] Refazendo Query Rápida (Tentativa {tentativa+1})...")
        res = gerar_texto_draft(prompt)
        q = res.replace('"', '').replace('\n', '').strip() if res else "anime scene"
        if q not in historico_queries:
            historico_queries.add(q)
            return q
        prompt = prompt_base + f"\n[SYSTEM ALERT]: You generated '{q}' which is in the FORBIDDEN list. Try again with a DIFFERENT visual trait."
    return q + " alternate"

def gerar_resumo_contexto(palavras):
    texto_completo = " ".join([p['palavra'] for p in palavras])
    if len(texto_completo) > 4000:
        texto_completo = texto_completo[:2000] + " ... [trecho omitido] ... " + texto_completo[-2000:]
    prompt = f"""Leia esta transcrição de um vídeo sobre Naruto/Boruto e forneça um resumo SUPER CURTO (máximo 2 linhas).
Foque apenas em responder: Qual é o tema central e quem são os personagens principais envolvidos?
Isso servirá de contexto para um diretor de arte buscar imagens. Não use formatação, apenas o texto direto.

Transcrição:{texto_completo}"""
    if DEBUG_MODE: print("      [DEBUG] Gerando Contexto Global do roteiro...")
    res = gerar_texto_draft(prompt)
    return res.strip() if res else "Vídeo focado no universo de Naruto/Boruto."

def transcrever_e_direcionar(audio_path):
    print("\n[1/5] Extraindo palavras com tempos cirurgicos...")
    palavras = transcrever_audio_hibrido(audio_path)
            
    print("\n[1.2/5] Mapeando o Contexto Global do Vídeo...")
    contexto_geral = gerar_resumo_contexto(palavras)
    if DEBUG_MODE: print(f"      [DEBUG] Contexto Global estabelecido: {contexto_geral}\n")

    TAMANHO_CHUNK = 5000
    total_palavras = len(palavras)
    historico_queries = set()
    master_json_global = []

    total_partes = (total_palavras + TAMANHO_CHUNK - 1) // TAMANHO_CHUNK

    for indice_chunk in range(0, total_palavras, TAMANHO_CHUNK):
        parte_atual = (indice_chunk // TAMANHO_CHUNK) + 1
        
        chunk_palavras = palavras[indice_chunk : indice_chunk + TAMANHO_CHUNK]
        id_inicio_chunk = indice_chunk
        id_fim_chunk = indice_chunk + len(chunk_palavras) - 1
        tempo_inicio_chunk = chunk_palavras[0]['inicio']
        tempo_fim_chunk = chunk_palavras[-1]['fim']
        
        duracao_chunk = tempo_fim_chunk - tempo_inicio_chunk
        ritmo_10s = (len(chunk_palavras) / duracao_chunk) * 10 if duracao_chunk > 0 else 20
        bpm_matematico = int(ritmo_10s * 6)
        
        dica_ritmo = f"PACING METRIC: The narrator is speaking {ritmo_10s:.1f} words per 10 secs (Approx {bpm_matematico} BPM). \n- FAST PACING (>24 words/10s): HIGHLY RECOMMEND 'Raiva' (for intense/villain/action) or 'Animado/Vibrante' (for hype/heroic). ABSOLUTELY PROHIBITED to use Calmo or Melancólico.\n- SLOW PACING (<16 words/10s): PROHIBITED to use Animado, Vibrante, or Raiva."
        
        texto_com_ids_chunk = " ".join([f"[{id_inicio_chunk + idx}] {p['palavra']}" for idx, p in enumerate(chunk_palavras)])
        lista_proibida = ", ".join(historico_queries) if historico_queries else "None"
        
        if total_partes == 1:
            contexto_progresso = f"PROGRESS: This is the full script. Start at ID 0 and process up to ID {id_fim_chunk}."
        elif parte_atual == 1:
            contexto_progresso = f"PROGRESS: This video is long, so this is PART 1 of {total_partes}. Start at ID 0 (0.00 seconds) and process up to ID {id_fim_chunk}."
        else:
            contexto_progresso = f"PROGRESS: This is PART {parte_atual} of {total_partes}. The previous part ended at ID {id_inicio_chunk - 1}. You are currently at {tempo_inicio_chunk:.2f} SECONDS into the video. START processing from ID {id_inicio_chunk} to ID {id_fim_chunk}."

        print(f"\n[1.5/5] Analisando Roteiro (Parte {parte_atual}/{total_partes}) - Estagiário Junior...")

        prompt_junior = f"""Act as a Junior Art Director for a Naruto/Boruto YouTube channel.
CONTEXT: "{contexto_geral}"
{contexto_progresso}

{dica_ritmo}

NARRATION WITH IDs: {texto_com_ids_chunk}

GOAL: Slice the IDs into logical visual scenes with search queries in ENGLISH.

STRICT RULES (FAILURE TO FOLLOW DESTRAYS THE VIDEO):

1. PROPER NOUN ISOLATION & EXACT REVEAL SYNCHRONIZATION (CRITICAL):
   - Every time a proper noun (e.g., "Orochimaru", "Naruto", "Mitsuki") or a specific title (e.g., "Terceiro Hokage", "Quarto Kazekage", "autor") is mentioned, you MUST create a dedicated scene for EACH of those names/terms.
   - REVEAL SYNC: The 'id_inicio' of a proper noun's scene MUST be the EXACT ID where that name is first spoken. DO NOT absorb preceding filler words into the proper noun's scene. Absorb preceding words into the PREVIOUS scene.
   - DEFAULT SUBJECT FALLBACK: For other contexts (without proper nouns), group the IDs normally. The visual query MUST be a PHYSICAL, TANGIBLE subject. If the text is abstract (e.g., "isso é benéfico", "de que os"), DO NOT invent abstract queries. Instead, use the MAIN character of the context (e.g., "Orochimaru Boruto anime screenshot").

2. PACING & DURATION (STOP OVER-SLICING):
   - A normal scene SHOULD cover 4 to 12 IDs combined (approx. 1.5s to 3.0s). 
   - NEVER create a scene for 1 or 2 words unless it is strictly to isolate a proper noun starting at that ID.
   - Standalone connectors and short prepositions (e.g., "e", "na", "os", "do", "que") MUST be absorbed into the adjacent visual scene. They can NEVER have their own query.
   - Combine TRAILING filler words, connectors, and verbs into the current scene until a NEW proper noun appears.

3. ATOMIC SEARCH & ZERO ABSTRACTIONS (ONE SUBJECT PER SCENE): 
   - NEVER include two characters or titles in the same query. DO NOT use "and" or "with". 
   - PROHIBITED WORDS (DO NOT USE): "concept", "story", "explanation", "punishment", "consequences", "actions", "deeds", "justification", "utility", "situation", "truth", "data", "reason".
   - SIMPLE ACTIONS: You MAY include simple physical actions (e.g., "fighting", "running", "smiling"). DO NOT use complex interaction verbs (e.g., "watching someone", "explaining", "discussing").

4. VISUAL FOCUS & ENTITIES (LIGHT NOVELS): 
   - If a Light Novel, Book, or Manga is mentioned (e.g., "Light Novel Sasuke Shinden"), you MUST group the entire entity name into ONE single scene (e.g., IDs 14 to 18) and create a specific query for its cover (e.g., "Sasuke Shinden light novel cover").

5. IMAGE AVAILABILITY & FALLBACK (AVOID BLACK SCREENS):
   - When generating queries for specific fictional scenes, append "anime screenshot" or "hq" to the query to ensure image availability. 
   - EXCEPTION (REAL PEOPLE): NEVER append "anime screenshot" or era suffixes to real people. For the author, use ONLY "Masashi Kishimoto".

6. CHRONOLOGICAL PRECISION & BLACKLIST:
   - Output the 'query' STRICTLY in ENGLISH. Output 'id_inicio' and 'id_fim' as integers.
   - Chronology: Add correct era suffix ("Naruto Classic", "Naruto Shippuden", "Boruto anime") based on the event.
   - Forbidden terms: "you", "narrator", "author", "then", "context", "subscribe", "video", "people", "other ninjas".
   - Substitution: Replace "Author" with "Masashi Kishimoto".

7. ANTI-REPETITION & VISUAL VARIETY (CRITICAL):
   - You are STRICTLY FORBIDDEN from outputting the exact same 'query' string twice in the same response. 
   - If you must use the same character fallback multiple times, you MUST append a unique visual descriptor each time (e.g., "Orochimaru sinister smile", "Orochimaru profile face", "Orochimaru shadow", "Orochimaru mysterious look") to force the search engine to provide different images.

8. GLOBAL MEMORY & FORBIDDEN QUERIES (DO NOT REPEAT):
   - You MUST NOT use any of these previously generated queries in this video: [{lista_proibida}]

9. BGM MOOD (THEME + PACING): Add a 'bgm_mood' to EVERY scene. Options: Raiva, Animado, Calmo, Sombrio, Dramático, Vibrante, Alegre, Inspirador, Romântico, Melancólico.
   - PACING SYNC: If the pacing is FAST (>24), you MUST default to 'Raiva' (if the context is aggressive, villainous, like Orochimaru, or battles) or 'Animado/Vibrante' (if the context is heroic or hype). 
   - If the pacing is SLOW or average, and the theme is dark/villainous, use 'Sombrio' or 'Dramático'.

10. KEEP EMOTIONAL FLOW: Keep the same 'bgm_mood' for consecutive scenes if the emotional tone hasn't changed. Do not change the mood every 2 seconds, but keep it at least 10-15 seconds.

11. REAL-WORLD SEARCHABILITY (ANTI-AI PROMPT):
   - Queries MUST be findable on standard Google Images. Do NOT write prompts for Midjourney/DALL-E.
   - DO NOT use hyper-specific AI modifiers (e.g., "cinematic lighting", "8k", "masterpiece", "epic low angle").
   - Stick to Subject + Basic Action/State + "anime screenshot" (e.g., "Orochimaru sinister smile anime screenshot"). Generic is better for search engines.

EXAMPLE OF PROPER GROUPING AND FALLBACK:
Text: "[25] de [26] que [27] os [28] dados [29] coletados [30] por [31] Yamato"
[
  {{"id_inicio": 25, "id_fim": 30, "query": "Orochimaru close up Boruto anime screenshot", "bgm_mood": "Sombrio"}},
  {{"id_inicio": 31, "id_fim": 31, "query": "Yamato Naruto Shippuden anime screenshot", "bgm_mood": "Sombrio"}}
]

Return ONLY the JSON array."""
        
        res_diretor = gerar_texto_draft(prompt_junior)
        draft_json_chunk = extrair_json_seguro(res_diretor) if res_diretor else []
        
        if DEBUG_MODE and draft_json_chunk: print(f"      [DEBUG] ✅ Rascunho da Parte {parte_atual} Gerado")
        time.sleep(2)

        print(f"[1.8/5] Revisão Mestra (Parte {parte_atual}/{total_partes}) - Diretor Sênior Gemini...")
        prompt_revisao = f"""You are the Master Art Director (Gemini).
A junior AI generated a draft of visual scenes for A CHUNK OF A VIDEO. Your job is to audit and COMPLETELY RECONSTRUCT the JSON to meet professional YouTube pacing and retention.
You have ABSOLUTE POWER to add, remove, split, or replace search queries to perfectly match the narration.

{contexto_progresso}

{dica_ritmo}

FULL TRANSCRIPTION FOR THIS CHUNK: {texto_com_ids_chunk}

JUNIOR'S DRAFT JSON FOR THIS CHUNK:{json.dumps(draft_json_chunk, indent=2) if draft_json_chunk else "[]"}

ORIGINAL RULES YOU MUST ENFORCE AND PERFECT:
1. EXTREME HIGH-DENSITY PACING (CRITICAL): The Junior often makes scenes too long. The final video MUST have between 50 and 90 scenes for every minute of video (roughly 180 IDs). Long scenes MUST be split into multiple fast-paced beats.Target approx 3 scenes or more per 10 IDs.
2. EXACT SYNC: Ensure the visual query perfectly represents the specific words spoken at those exact IDs. Proper nouns MUST trigger exactly on the ID they are spoken. If the Junior missed a sync, fix the 'id_inicio'.
3. NO ABSTRACTIONS: Queries must be physical things. Replace abstract queries (like "isso é benéfico", "data", "utility") with tangible character actions.
4. NO GAPS (ZERO BLACK SCREENS): Ensure there are NO MISSING IDs between scenes. The timeline must be 100% covered from ID {id_inicio_chunk} to ID {id_fim_chunk}. If the Junior left a gap, YOU MUST CREATE a new scene to fill it.
5. NO REPETITIONS: Every single query MUST be unique. Use different camera angles/descriptors (e.g., "Orochimaru close up", "Orochimaru walking", "Orochimaru sinister smile").
6. THEMATIC RESTRICTION (NARUTO/BORUTO ONLY): You are ONLY allowed to use images from the Naruto/Boruto universe. Absolutely NO outside anime or generic images are allowed, with ONE exception: if absolutely necessary to illustrate something obscure, ONE image from another anime is permitted. Exceptions are made only for real cited people (like Masashi Kishimoto) or real things.
7. THEMATIC OPENING: The very first images of the video MUST relate directly to the general theme. For example, if the overall video is about Orochimaru, the first search queries must feature Orochimaru.
8. PRONOUN RESOLUTION & SPLIT CHARACTERS: Direct mentions (e.g., "Minato"), indirect mentions (e.g., "Fourth Hokage"), and pronouns (e.g., "he", "him") MUST trigger an image of that exact character on the exact ID(s) they are spoken, even if just for 0.5 seconds. You MUST infer who the pronoun refers to from the context. NEVER group characters together in a single query (e.g., do not use "Kakashi and Naruto"); instead, create separate, rapid queries for each character tied to their respective IDs.
9. HIGH-DEFINITION AESTHETICS GUARANTEED: The backend image extraction engine now mathematically guarantees HD quality (720p+). You do NOT need to worry about basic image availability. Focus 100% on providing the most visually striking descriptors possible.
10. GLOBAL MEMORY (CRITICAL): Do NOT reuse these queries from previous parts: [{lista_proibida}]
11. BGM MOOD VERIFICATION (THEME & PACING): Audit the 'bgm_mood'. 
    - FAST PACING OVERRIDE: Fast speech (>24 words/10s) MUST trigger high-energy moods. If the text is about villains, crimes, or fights at high speed, FORCE the mood to 'Raiva'. If it's about heroes or hype, FORCE it to 'Animado' or 'Vibrante'.
    - SLOW/DARK OVERRIDE: If the pacing allows, dark themes (Orochimaru, tragedies) should use 'Sombrio' or 'Dramático'. NEVER use 'Calmo' or 'Alegre' for villains.
    - Group consecutive scenes into the same mood to avoid abrupt music changes.
12. REAL-WORLD SEARCH ENGINE COMPATIBILITY (ANTI-AI PROMPT):
    - While keeping the scene dynamic, the query MUST actually exist on Google Images (like a wiki or crunchyroll screenshot).
    - AVOID overly complex, multi-layered AI-style descriptions (e.g., remove "cinematic lighting, dramatic shadows, 4k resolution").
    - Focus on the Character, the specific Action/Emotion, and the Anime Era. Generic enough to be found, specific enough to be accurate.

YOUR TASK:
1. First, write a brief, harsh text analysis of the Junior's pacing, sync errors, gaps, repetitions, and total scene count.
2. Then, output the ENTIRE corrected, gapless, and highly dynamic JSON array for this specific chunk.

OUTPUT FORMAT:
[Your text analysis here]
```json
[
  {{"id_inicio": {id_inicio_chunk}, "id_fim": {id_inicio_chunk + 3}, "query": "...", "bgm_mood": "Vibrante"}},
  {{"id_inicio": {id_inicio_chunk + 4}, "id_fim": {id_inicio_chunk + 6}, "query": "...", "bgm_mood": "Vibrante"}}
]
```"""
        res_revisao = gerar_texto_revisor(prompt_revisao)
        
        if DEBUG_MODE and res_revisao: print(f" [DEBUG] ANÁLISE GEMINI (PARTE {parte_atual}):\n{res_revisao}\n")

        dados_json_final = extrair_json_seguro(res_revisao)
        
        # Consolidação do Array Mestre Global COM INJEÇÃO MATEMÁTICA DE BPM
        if dados_json_final:
            for cena_json in dados_json_final: 
                cena_json['bgm_bpm'] = bpm_matematico # Injeção infalível do Python
            master_json_global.extend(dados_json_final)
            for c in dados_json_final: historico_queries.add(c.get('query', ''))
        else:
            if DEBUG_MODE: print("      [DEBUG] Gemini falhou no JSON. Usando Rascunho do Junior.")
            for cena_json in draft_json_chunk:
                cena_json['bgm_bpm'] = bpm_matematico # Injeção infalível do Python
            master_json_global.extend(draft_json_chunk)
            for c in draft_json_chunk: historico_queries.add(c.get('query', ''))
            
        if parte_atual < total_partes:
            espera = 20
            print(f"      [Aviso] Resfriando motores da API por {espera}s para evitar limite de Tokens Por Minuto (TPM)...")
            time.sleep(espera)

    print("\n[1.9/5] Montando a Timeline Global (Ancoragem Absoluta sobre o roteiro todo)...")
    cenas_visuais = [] 
    if master_json_global:
        dados_json = sorted(master_json_global, key=lambda x: x.get('id_inicio', 0))
        id_atual_esperado = 0
        cenas_ancoradas = []
        
        for cena in dados_json:
            id_in = cena.get('id_inicio', id_atual_esperado)
            id_out = cena.get('id_fim', id_in)
            
            if id_in > id_atual_esperado: id_in = id_atual_esperado
                
            id_in = max(0, min(id_in, len(palavras) - 1))
            id_out = max(id_in, min(id_out, len(palavras) - 1))
            
            inicio_real = palavras[id_in]['inicio']
            fim_real = palavras[id_out]['fim']
            texto_exato_falado = " ".join([p['palavra'] for p in palavras[id_in:id_out+1]])
            
            cenas_ancoradas.append({
                "inicio": inicio_real,
                "fim": fim_real,
                "texto": texto_exato_falado,
                "query": cena.get('query', 'anime scene'),
                "id_rastreio": f"[{id_in} ao {id_out}]",
                "bgm_bpm": cena.get('bgm_bpm', 120),
                "bgm_mood": cena.get('bgm_mood', 'Calmo')
            })
            id_atual_esperado = id_out + 1
            
        if id_atual_esperado < len(palavras):
            id_in = id_atual_esperado
            id_out = len(palavras) - 1
            texto_cauda = " ".join([p['palavra'] for p in palavras[id_in:]])
            query_cauda = obter_query_rapida(texto_cauda, historico_queries)
            
            cenas_ancoradas.append({
                "inicio": palavras[id_in]['inicio'],
                "fim": palavras[id_out]['fim'],
                "texto": texto_cauda,
                "query": query_cauda,
                "id_rastreio": f"[{id_in} ao {id_out}]",
                "bgm_bpm": 120,
                "bgm_mood": "Calmo"
            })

        for k in range(len(cenas_ancoradas) - 1):
            cenas_ancoradas[k]['fim'] = cenas_ancoradas[k+1]['inicio']

        for cena in cenas_ancoradas:
            duracao_cena = cena['fim'] - cena['inicio']
            if duracao_cena > 3.0:
                inicio_fatiado = cena['inicio']
                while duracao_cena > 0:
                    fatia = min(3.0, duracao_cena)
                    cenas_visuais.append({
                        "inicio": inicio_fatiado, 
                        "fim": inicio_fatiado + fatia,
                        "texto": cena['texto'], 
                        "query": cena['query'],
                        "id_rastreio": cena['id_rastreio'] + " (Fatiada)",
                        "bgm_bpm": cena['bgm_bpm'],
                        "bgm_mood": cena['bgm_mood']
                    })
                    inicio_fatiado += fatia
                    duracao_cena -= fatia
            else:
                cenas_visuais.append(cena)
                
    else:
        inicio_temp = palavras[0]['inicio']
        fim_real_bloco = palavras[-1]['fim']
        while inicio_temp < fim_real_bloco:
            fim_temp = min(inicio_temp + 3.0, fim_real_bloco)
            palavras_pedaco = [bp['palavra'] for bp in palavras if bp['inicio'] >= inicio_temp and bp['inicio'] < fim_temp]
            texto_pedaco = " ".join(palavras_pedaco)
            query_pedaco = obter_query_rapida(texto_pedaco, historico_queries) if texto_pedaco.strip() else "Naruto context"
                
            cenas_visuais.append({
                "inicio": inicio_temp, "fim": fim_temp, 
                "texto": texto_pedaco, "query": query_pedaco, 
                "id_rastreio": "[Fallback]", "bgm_bpm": 120, "bgm_mood": "Calmo"
            })
            inicio_temp = fim_temp

    return cenas_visuais