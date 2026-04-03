import os
import json
import time
import re
import requests
import gc
import platform
from google import genai
import ollama
from faster_whisper import WhisperModel
from configuracoes import *

# --- DETECÇÃO DE SISTEMA E BLINDAGEM DE CPU ---
SISTEMA = platform.system()

if SISTEMA == "Linux":
    # Coloca uma coleira em bibliotecas matemáticas subjacentes no Colab (2 vCPUs)
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"

# =====================================================================
# FUNÇÕES DE INFRAESTRUTURA DE IA
# =====================================================================

def chamar_groq_texto(prompt, model_name, max_tentativas=3):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "top_p": 0.01,
        "response_format": {"type": "json_object"} 
    }
    for tentativa in range(max_tentativas):
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 429:
            if DEBUG_MODE: print(f"      [Aviso Groq] Limite atingido. Pausando 30s ({tentativa + 1}/{max_tentativas})...")
            time.sleep(30)
            continue
        res.raise_for_status()
        return res.json()['choices'][0]['message']['content']
    raise Exception(f"Falha no Groq para o modelo {model_name}.")

def gerar_texto_draft(prompt, formato_json=True):
    for plataforma, modelo in FALLBACK_TEXTO:
        if DEBUG_MODE: print(f"      [DEBUG] [Texto Draft] Usando Nuvem: {modelo}")
        try:
            if plataforma == "groq" and GROQ_KEY:
                return chamar_groq_texto(prompt, modelo)
        except Exception: continue
            
    vram, ram = obter_recursos_sistema()
    modelo_local = escolher_modelo_junior(vram, ram)
    try:
        opcoes = {'temperature': 0.0, 'keep_alive': 0}
        if formato_json: opcoes['format'] = 'json'
        res = ollama.chat(model=modelo_local, messages=[{'role': 'user', 'content': prompt}], options=opcoes)
        descarregar_modelo_ollama(modelo_local) 
        gc.collect()
        
        # --- A TESOURA DE RACIOCÍNIO ---
        resposta_bruta = res['message']['content']
        resposta_limpa = re.sub(r'<think>.*?</think>', '', resposta_bruta, flags=re.DOTALL).strip()
        return resposta_limpa
    except Exception as e:
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

                try:
                    client = genai.Client(api_key=key)
                    res = client.models.generate_content(
                        model=modelo, 
                        contents=prompt, 
                        config={'temperature': 0.0, 'top_p': 0.01, 'response_mime_type': 'application/json'}
                    )
                    return res.text
                except Exception as e:
                    erro_str = str(e).lower()
                    if "perminute" in erro_str or "retry in" in erro_str or "429" in erro_str:
                        if "perday" in erro_str: ESTADO_REVISOR['gemini_permanentes'].add((key_idx, model_idx))
                        else: ESTADO_REVISOR['gemini_cooldowns'][(key_idx, model_idx)] = time.time() + 60
                    else: ESTADO_REVISOR['gemini_permanentes'].add((key_idx, model_idx))
                    usou_gemini = True

        if len(ESTADO_REVISOR['gemini_permanentes']) >= len(API_KEYS) * len(GEMINI_REVISOR_MODELS):
            ESTADO_REVISOR['gemini_esgotado'] = True

    while ESTADO_REVISOR['fallback_idx'] < len(FALLBACK_TEXTO):
        plataforma, modelo = FALLBACK_TEXTO[ESTADO_REVISOR['fallback_idx']]
        try:
            if plataforma == "groq" and GROQ_KEY: return chamar_groq_texto(prompt, modelo)
            else:
                ESTADO_REVISOR['fallback_idx'] += 1
                continue
        except Exception: ESTADO_REVISOR['fallback_idx'] += 1

    vram, ram = obter_recursos_sistema()
    modelo_local = escolher_modelo_senior(vram, ram)
    try:
        res = ollama.chat(model=modelo_local, messages=[{'role': 'user', 'content': prompt}], options={'temperature': 0.0, 'keep_alive': 0, 'format': 'json'})
        descarregar_modelo_ollama(modelo_local) 
        
        # --- A TESOURA DE RACIOCÍNIO ---
        resposta_bruta = res['message']['content']
        resposta_limpa = re.sub(r'<think>.*?</think>', '', resposta_bruta, flags=re.DOTALL).strip()
        return resposta_limpa
    except Exception:
        descarregar_modelo_ollama(modelo_local)
        return ""

def _processar_chunk_whisper(audio_path):
    if GROQ_KEY:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}"}
        for modelo in WHISPER_MODELS:
            for tentativa in range(3):
                try:
                    with open(audio_path, "rb") as file:
                        files = {"file": (os.path.basename(audio_path), file, "audio/mpeg")}
                        data = {"model": modelo, "response_format": "verbose_json", "timestamp_granularities[]": "word", "language": "pt"}
                        res = requests.post(url, headers=headers, files=files, data=data, timeout=60)
                        if res.status_code == 429:
                            time.sleep(60)
                            continue
                        res.raise_for_status()
                        resultado = res.json()
                        if "words" in resultado:
                            return [{"palavra": w["word"].strip(), "inicio": w["start"], "fim": w["end"]} for w in resultado["words"]]
                except Exception: pass
            
    vram, ram = obter_recursos_sistema()
    modelo_whisper = escolher_modelo_whisper(vram, ram)
    device_type = "cuda" if vram >= 1.0 else "cpu"
    comp_type = "float16" if vram >= 1.0 else "int8"
    
    # --- LIMITADOR DE THREADS DE CPU PARA O COLAB ---
    threads_cpu = 2 if SISTEMA == "Linux" else 4
    
    model = WhisperModel(
        modelo_whisper, 
        device=device_type, 
        compute_type=comp_type, 
        cpu_threads=threads_cpu
    )
    
    vocabulario = "Naruto, Orochimaru, Konoha, Sasuke, Mitsuki, Boruto, Shin, Yamato, Uchiha, Hokage, Rasengan, Chidori, Sharingan, Light Novel"
    
    segments, _ = model.transcribe(audio_path, word_timestamps=True, initial_prompt=vocabulario, vad_filter=True)
    resultados = [{"palavra": w.word.strip(), "inicio": w.start, "fim": w.end} for s in segments for w in s.words]
    
    del model
    gc.collect()
    return resultados

def transcrever_audio_hibrido(audio_path):
    from moviepy.editor import AudioFileClip
    clip_mestre = AudioFileClip(audio_path)
    duracao_total = clip_mestre.duration
    tamanho_arquivo_mb = os.path.getsize(audio_path) / (1024 * 1024)
    limite_seguro_mb = 22.0
    
    if tamanho_arquivo_mb > limite_seguro_mb:
        tamanho_chunk_seg = duracao_total * (limite_seguro_mb / tamanho_arquivo_mb)
    else:
        tamanho_chunk_seg = duracao_total + 1.0 

    resultados_globais = []
    if duracao_total <= tamanho_chunk_seg:
        resultados_globais = _processar_chunk_whisper(audio_path)
    else:
        for inicio_chunk in range(0, int(duracao_total), int(tamanho_chunk_seg)):
            fim_chunk = min(inicio_chunk + tamanho_chunk_seg, duracao_total)
            subclip = clip_mestre.subclip(inicio_chunk, fim_chunk)
            temp_path = f"temp_whisper_chunk_{inicio_chunk}.mp3"
            subclip.write_audiofile(temp_path, bitrate="64k", logger=None)
            
            resultados_chunk = _processar_chunk_whisper(temp_path)
            if resultados_chunk:
                for r in resultados_chunk:
                    r['inicio'] += inicio_chunk
                    r['fim'] += inicio_chunk
                    resultados_globais.append(r)
            os.remove(temp_path)
            
    clip_mestre.close()
    return resultados_globais

def extrair_json_seguro(texto):
    try:
        match = re.search(r'\[.*\]|\{.*\}', texto, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(texto)
    except:
        return None

# =====================================================================
# NOVA ARQUITETURA: MATEMÁTICA + PREENCHIMENTO DE LACUNAS BLINDADO
# =====================================================================

def mapear_contexto_e_entidades(palavras):
    texto_completo = " ".join([p['palavra'] for p in palavras]) 
    
    if len(texto_completo) > 30000:
        if DEBUG_MODE: print("      [AVISO] Áudio gigantesco detectado. Resumindo...")
        texto_completo = texto_completo[:15000] + " ... [trecho central longo omitido] ... " + texto_completo[-15000:]
    
    prompt = f"""Read this FULL video transcript: '{texto_completo}'
    
    Analyze the ENTIRE text and return ONLY a JSON object with two keys:
    1. "contexto": ONLY the exact Name of the Franchise or Main Topic. DO NOT write sentences. (e.g. use "Naruto", "Bleach", "Finance". NEVER use "Naruto anime lore", "Video about Bleach").
    2. "entidades": A list of ALL proper nouns mentioned (Characters, places, jutsus, real people).
    
    STRICT RULES FOR ENTITIES:
    - GOOD: "Naruto", "Konoha", "Steve Jobs", "Apple", "Sharingan".
    - BAD (FORBIDDEN): "lore", "anime", "battle", "money", "sword", "hero", "scene".
    
    FORMAT YOUR RESPONSE EXACTLY AS THIS JSON:
    {{
      "contexto": "Franchise Name ONLY",
      "entidades": ["Name1", "Name2"]
    }}"""
    
    res = gerar_texto_draft(prompt, formato_json=True)
    dados = extrair_json_seguro(res)
    
    if dados and isinstance(dados, dict):
        contexto = dados.get('contexto', 'Generic Theme')
        entidades = dados.get('entidades', [])
        entidades_limpas = [re.sub(r'[^\w\s]', '', e).lower() for e in entidades]
        return contexto, entidades_limpas
    
    return "Generic Theme", []

def obter_query_rapida(texto, contexto_geral, historico_queries=None):
    if historico_queries is None: historico_queries = set()
    proibidas = ", ".join(historico_queries) if historico_queries else "None"
    
    prompt_base = f"""Read this short text: '{texto}'.
    CONTEXT OF THE VIDEO: "{contexto_geral}"
    
    TASK: Generate an image search query.
    STRICT RULES:
    1. LANGUAGE: STRICTLY ENGLISH. NO Portuguese.
    2. BANNED WORDS: NEVER use words like "lore", "epic", "scene", "anime", "4k", "sad", "beautiful".
    3. THEME ANCHORING (CRITICAL): The LAST WORD of your query MUST be the franchise/universe name (e.g., "{contexto_geral}").
    4. FORMAT: [Subject] + [Franchise]. Max 4 words. Physical and visual only.
    5. FORBIDDEN QUERIES: [{proibidas}]
    
    Query:"""
    
    prompt = prompt_base
    for tentativa in range(3):
        res = gerar_texto_draft(prompt, formato_json=False)
        q = res.replace('"', '').replace('\n', '').strip() if res else f"character {contexto_geral}"
        if q not in historico_queries:
            historico_queries.add(q)
            return q
        prompt = prompt_base + f"\n[SYSTEM ALERT]: You generated '{q}' which is in the FORBIDDEN list. Try again."
    return q + " alternate"

def construir_esqueleto_matematico(palavras, entidades_alvo, tempo_por_cena=3.0):
    esqueleto_cenas = []
    total_palavras = len(palavras)
    i = 0
    id_cena_global = 0

    while i < total_palavras:
        palavra_atual = re.sub(r'[^\w\s]', '', palavras[i]['palavra']).lower()
        
        if palavra_atual in entidades_alvo and len(palavra_atual) > 2:
            id_start = max(0, i - 1)
            id_end = min(total_palavras - 1, i + 1)
            
            if esqueleto_cenas and id_start <= esqueleto_cenas[-1]['id_fim']:
                id_start = esqueleto_cenas[-1]['id_fim'] + 1
            if id_start > id_end: id_start = id_end
                
            texto_cena = " ".join([p['palavra'] for p in palavras[id_start:id_end+1]])
            
            esqueleto_cenas.append({
                "id_cena": id_cena_global,
                "id_inicio": id_start,
                "id_fim": id_end,
                "texto": texto_cena,
                "query": "", 
            })
            id_cena_global += 1
            i = id_end + 1
            continue

        id_start = i
        tempo_inicio = palavras[i]['inicio']
        j = i
        
        while j < total_palavras:
            tempo_atual = palavras[j]['fim']
            proxima_palavra = re.sub(r'[^\w\s]', '', palavras[j]['palavra']).lower()
            
            if (tempo_atual - tempo_inicio >= tempo_por_cena) or (proxima_palavra in entidades_alvo and len(proxima_palavra) > 2 and j > i):
                break
            j += 1
            
        if j >= total_palavras: j = total_palavras - 1
        elif (palavras[j]['fim'] - tempo_inicio >= tempo_por_cena): pass
        else: j = max(i, j - 1)
            
        texto_cena = " ".join([p['palavra'] for p in palavras[id_start:j+1]])
        
        esqueleto_cenas.append({
            "id_cena": id_cena_global,
            "id_inicio": id_start,
            "id_fim": j,
            "texto": texto_cena,
            "query": "", 
        })
        id_cena_global += 1
        i = j + 1
        
    return esqueleto_cenas

def calcular_matematica_musical(cenas, palavras):
    for cena in cenas:
        id_in = cena['id_inicio']
        id_out = cena['id_fim']
        duracao = palavras[id_out]['fim'] - palavras[id_in]['inicio']
        qtde_palavras = (id_out - id_in) + 1
        
        # PYTHON DECIDE O BPM
        ritmo_10s = (qtde_palavras / duracao) * 10 if duracao > 0 else 20
        cena['bgm_bpm'] = int(ritmo_10s * 6)
        
        # Mantemos o Mood da IA intacto. Se ela falhou, colocamos Neutro.
        if 'bgm_mood' not in cena or not cena['bgm_mood']:
            cena['bgm_mood'] = "Neutro"
        
        cena['inicio'] = palavras[id_in]['inicio']
        cena['fim'] = palavras[id_out]['fim']
        cena['id_rastreio'] = f"[{id_in} ao {id_out}]"

def transcrever_e_direcionar(audio_path, tempo_alvo=3.0):
    print("\n[1/5] Extraindo palavras com tempos cirurgicos...")
    palavras = transcrever_audio_hibrido(audio_path)
            
    print("\n[1.2/5] Mapeando o Contexto Global e Entidades...")
    contexto_geral, entidades = mapear_contexto_e_entidades(palavras)
    if DEBUG_MODE: 
        print(f"      [DEBUG] Tema Global: {contexto_geral}")
        print(f"      [DEBUG] Entidades Blindadas: {len(entidades)} encontradas.")

    # AQUI O PYTHON USA O TEMPO ESCOLHIDO PELO USUÁRIO!
    print(f"\n[1.3/5] Construindo a Timeline (Matemática Pura -> {tempo_alvo}s por cena)...")
    esqueleto = construir_esqueleto_matematico(palavras, entidades, tempo_por_cena=tempo_alvo)
    
    print(f"      [SISTEMA] Esqueleto gerado com sucesso: {len(esqueleto)} cenas planejadas.")

    print("\n[1.5/5] Invocando LLM para Preenchimento de Lacunas (Branching Prompts)...")
    
    TAMANHO_LOTE = 100 
    total_lotes = (len(esqueleto) + TAMANHO_LOTE - 1) // TAMANHO_LOTE
    historico_queries = set()
    
    # ---------------------------------------------------------
    # RAMIFICAÇÃO DE PROMPTS POR CATEGORIA
    # ---------------------------------------------------------
    tema_lower = contexto_geral.lower()
    
    if "naruto" in tema_lower or "boruto" in tema_lower:
        prompt_template = f"""You are a Master Art Director for a Naruto/Boruto YouTube channel. Read this JSON array sequentially. 
YOUR TASK: Fill BOTH the "query" and "bgm_mood" fields for each object.

GLOBAL CONTEXT: "{contexto_geral}"

STRICT RULES (FAILURE DESTROYS THE VIDEO):
1. LANGUAGE: STRICTLY ENGLISH for "query". 
2. NO FLUFF: BANNED WORDS: "lore", "epic", "scene", "anime", "sad", "emotional", "background", "concept". Use ONLY raw physical nouns/actions.
3. THEMATIC ANCHORING (CRITICAL):
   - You MUST append the specific era suffix based on the exact event in the text: "Naruto Classic", "Naruto Shippuden", "Boruto anime", or "Boruto TBV".
   - If you don't know the era, append "{contexto_geral}".
4. PRONOUN RESOLUTION & ZERO ABSTRACTIONS: 
   - Replace "he/him" with the actual character name based on the ongoing text. 
   - Replace abstract queries (like "data" or "truth") with tangible actions (e.g., "Orochimaru sinister smile").
   - NEVER group characters (e.g., NO "Kakashi and Naruto").
5. BGM MOOD: You MUST choose EXACTLY ONE mood from this list: Raiva, Animado, Calmo, Sombrio, Dramático, Vibrante, Alegre, Inspirador, Romântico, Melancólico. Keep consecutive scenes with the same mood unless the emotion clearly shifts.
6. THE HOOK RULE: For "id_cena" 0, 1, or 2, the query MUST be exactly the MAIN SUBJECT of the video followed by the era.

FEW-SHOT EXAMPLES:
- Text (id_cena: 0): "Tudo começou há muito tempo..." -> Query: "[Main Subject] {contexto_geral}", Mood: "Sombrio"
- Text (id_cena: 45): "Orochimaru matou o terceiro Hokage" -> Query: "Orochimaru kills Hiruzen Naruto Classic", Mood: "Raiva"
- Text (id_cena: 47): "os dados coletados por Yamato" -> Query: "Yamato face Naruto Shippuden", Mood: "Dramático"

JSON TO FILL:
{{json_payload}}

OUTPUT ONLY THE COMPLETED JSON ARRAY."""

    elif "anime" in tema_lower or "manga" in tema_lower or "piece" in tema_lower or "bleach" in tema_lower or "dragon ball" in tema_lower:
        prompt_template = f"""You are a Master Art Director for an Anime YouTube channel. Read this JSON array sequentially. 
YOUR TASK: Fill BOTH the "query" and "bgm_mood" fields for each object.

GLOBAL CONTEXT: "{contexto_geral}"

STRICT RULES:
1. LANGUAGE: STRICTLY ENGLISH for "query". 
2. NO FLUFF: BANNED WORDS: "lore", "epic", "scene", "anime", "sad", "emotional", "background", "concept". Use ONLY raw physical nouns/actions.
3. MANDATORY ANCHORING: EVERY single query MUST end with the exact franchise name (e.g. "{contexto_geral}").
4. PRONOUN RESOLUTION & ZERO ABSTRACTIONS: Replace pronouns with character names. Replace abstract thoughts with physical actions (e.g., "thinking character {contexto_geral}").
5. BGM MOOD: You MUST choose EXACTLY ONE mood from this list: Raiva, Animado, Calmo, Sombrio, Dramático, Vibrante, Alegre, Inspirador, Romântico, Melancólico. 
6. THE HOOK RULE: For "id_cena" 0, 1, or 2, the query MUST be exactly the MAIN SUBJECT of the video followed by the franchise.

FEW-SHOT EXAMPLES (Assuming Context is Bleach):
- Text (id_cena: 0): "Bem vindos ao canal..." -> Query: "Ichigo Kurosaki Bleach", Mood: "Animado"
- Text (id_cena: 45): "uma batalha sangrenta ocorreu" -> Query: "sword fight Bleach", Mood: "Raiva"

JSON TO FILL:
{{json_payload}}

OUTPUT ONLY THE COMPLETED JSON ARRAY."""

    else:
        prompt_template = f"""You are a Master Art Director for YouTube. Read this JSON array sequentially. 
YOUR TASK: Fill BOTH the "query" and "bgm_mood" fields for each object.

GLOBAL CONTEXT: "{contexto_geral}"

STRICT RULES:
1. LANGUAGE: STRICTLY ENGLISH for "query". 
2. NO FLUFF: BANNED WORDS: "lore", "epic", "scene", "sad", "emotional", "background", "concept", "illustration", "4k". Use ONLY raw physical nouns/actions.
3. MANDATORY ANCHORING: EVERY single query MUST end with the topic: "{contexto_geral}".
4. HIGHLY VISUAL REALISM: Translate abstract text into physical, tangible real-world objects or people. NEVER use abstract queries like "economy". Use "stock market crash".
5. BGM MOOD: You MUST choose EXACTLY ONE mood from this list: Raiva, Animado, Calmo, Sombrio, Dramático, Vibrante, Alegre, Inspirador, Romântico, Melancólico.
6. THE HOOK RULE: For "id_cena" 0, 1, or 2, the query MUST be exactly the MAIN SUBJECT of the video followed by the topic.

FEW-SHOT EXAMPLES (Assuming Context is Finance):
- Text (id_cena: 0): "Hoje vamos falar sobre..." -> Query: "[Main Topic] Finance", Mood: "Inspirador"
- Text (id_cena: 45): "a economia afundou rapidamente" -> Query: "stock market crash Finance", Mood: "Dramático"

JSON TO FILL:
{{json_payload}}

OUTPUT ONLY THE COMPLETED JSON ARRAY."""

    for lote_idx in range(total_lotes):
        inicio_idx = lote_idx * TAMANHO_LOTE
        fim_idx = inicio_idx + TAMANHO_LOTE
        lote_cenas = esqueleto[inicio_idx:fim_idx]
        
        template_ia = [{"id_cena": c['id_cena'], "texto": c['texto'], "query": "", "bgm_mood": ""} for c in lote_cenas]
        
        prompt_final = prompt_template.replace("{json_payload}", json.dumps(template_ia, ensure_ascii=False))

        print(f"      -> Processando Lote {lote_idx + 1}/{total_lotes} (Tema: {contexto_geral})...")
        res_revisor = gerar_texto_revisor(prompt_final)
        lote_preenchido = extrair_json_seguro(res_revisor)
        
        if lote_preenchido:
            for cena_respondida in lote_preenchido:
                for cena_original in esqueleto:
                    if cena_original['id_cena'] == cena_respondida.get('id_cena'):
                        cena_original['query'] = cena_respondida.get('query', f'character {contexto_geral}')
                        cena_original['bgm_mood'] = cena_respondida.get('bgm_mood', 'Neutro')
                        historico_queries.add(cena_original['query'])
                        break
        else:
            if DEBUG_MODE: print("      [AVISO] Falha no JSON. Usando Fallback de query...")
            for c in lote_cenas: 
                c['query'] = f"{contexto_geral} visual"
                c['bgm_mood'] = "Neutro"
            
        time.sleep(2)

    print("\n[1.9/5] Ancoragem Absoluta da Timeline e Limpeza Final...")
    calcular_matematica_musical(esqueleto, palavras)
    
    for cena in esqueleto:
        if 'id_cena' in cena: del cena['id_cena']

    for k in range(len(esqueleto) - 1):
        esqueleto[k]['fim'] = esqueleto[k+1]['inicio']

    return esqueleto
