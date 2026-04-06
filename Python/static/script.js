let projetoAtual = null;
let timeline = null;
let itemsDataset = null;
let itemClicadoMenu = null;
let cenaAtivaPropriedades = -1; 
let groupsDataset = null;

let isPlaying = false;
const FPS = 30; 
let imageCache = {};
let timelinePlanificada = [];

let historyStack = [];
let historyIndex = -1;
let isUndoing = false;

let previewRaf = null;
let previewStartTime = 0;
let previewSfxNode = null;
let isPreviewing = false;

window._advMenuOpen = false;

// Rastreador Global da Tecla Shift para o Efeito Magnético
window.isShiftPressed = false;
document.addEventListener('keydown', (e) => { if (e.key === 'Shift') window.isShiftPressed = true; });
document.addEventListener('keyup', (e) => { if (e.key === 'Shift') window.isShiftPressed = false; });

window.gerarCabecalhoCamada = function(id, icone, texto, cor) {
    if (!projetoAtual) return '';
    if (!projetoAtual.volumes_camadas) projetoAtual.volumes_camadas = {};
    let vol = projetoAtual.volumes_camadas[id] !== undefined ? projetoAtual.volumes_camadas[id] : 1.0;
    
    return `
        <div style="display:flex; align-items:center; width:100%; justify-content:space-between; color:${cor}; padding-right: 5px;">
            <div style="display:flex; align-items:center;">
                <i class="${icone}" style="margin-right:6px; font-size:1.2em;"></i> ${texto}
            </div>
            <div class="track-vol-container">
                <i class="ph-fill ph-speaker-high track-vol-icon"></i>
                <div class="track-vol-slider-wrapper">
                    <input type="range" class="track-vol-slider" min="0" max="2" step="0.05" value="${vol}" 
                        oninput="mudarVolumeCamada('${id}', this.value)" 
                        onchange="pushHistory(); sincronizarJSON();"
                        onmousedown="event.stopPropagation();" 
                        ontouchstart="event.stopPropagation();" 
                        onpointerdown="event.stopPropagation();">
                </div>
            </div>
        </div>
    `;
};;

window.mudarVolumeCamada = function(id, valStr) {
    let val = parseFloat(valStr);
    if (!projetoAtual.volumes_camadas) projetoAtual.volumes_camadas = {};
    projetoAtual.volumes_camadas[id] = val;

    // Aplica o som em tempo real no navegador
    if (id === 'a1') {
        let gain = projetoAtual.volume_locucao !== undefined ? projetoAtual.volume_locucao : 1.0;
        if(AudioEngine.masterGain) AudioEngine.masterGain.gain.value = gain * val;
        if(window.desenharWaveform) window.desenharWaveform();
    } else if (id === 'a2') {
        if(typeof AudioEngine !== 'undefined' && AudioEngine.bgmGains) {
            projetoAtual.faixas_musicais.forEach((faixa, idx) => {
                if (faixa && AudioEngine.bgmGains[idx]) {
                    let vFaixa = faixa.volume !== undefined ? faixa.volume : 0.15;
                    AudioEngine.bgmGains[idx].gain.value = vFaixa * val;
                }
            });
        }
        if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas(); // <<< REDESENHA
    } else if (id.startsWith('v')) {
        projetoAtual.cenas.forEach((cena, idx) => {
                if (cena && cena.camada === id && imageCache[idx] && imageCache[idx] instanceof HTMLVideoElement) {
                    let vCena = cena.volume_video !== undefined ? cena.volume_video : 1.0;
                    imageCache[idx].volume = Math.min(vCena * val, 1.0); 
                }
            });
            
            // >>> ATUALIZA AS TRANSIÇÕES DA TIMELINE EM TEMPO REAL <<<
            if (typeof AudioEngine !== 'undefined' && AudioEngine.sfxGains) {
                AudioEngine.sfxGains.forEach(sfx => {
                    if (sfx.layer === id) sfx.node.gain.value = sfx.baseVol * val;
                });
            }
            // >>> ATUALIZA O PREVIEW DE TRANSIÇÃO (SE ESTIVER ABERTO) <<<
            if (window.previewSfxGainNode && window.previewSfxLayer === id) {
                window.previewSfxGainNode.gain.value = window.previewSfxBaseVol * val;
            }
        }
    };

const OPCOES_ANIMACAO = [
    { id: 'auto', icone: 'ph-robot', label: 'Aleatório' },
    { id: 'zoom_in', icone: 'ph-magnifying-glass-plus', label: 'Zoom In' },
    { id: 'zoom_out', icone: 'ph-magnifying-glass-minus', label: 'Zoom Out' },
    { id: 'pan', icone: 'ph-arrows-left-right', label: 'Pan' },
    { id: 'nenhuma', icone: 'ph-stop-circle', label: 'Parada' }
];

const OPCOES_TRANSICAO = [
    { id: 'auto', icone: 'ph-robot', label: 'Aleatória' },
    { id: 'zoom_rotacao', icone: 'ph-arrows-clockwise', label: 'Zoom Rotação' },
    { id: 'zoom_suave_paralaxe', icone: 'ph-video-camera', label: 'Zoom Suave' },
    { id: 'warp_zoom', icone: 'ph-rocket-launch', label: 'Warp Zoom' },
    { id: 'buraco_de_minhoca', icone: 'ph-spiral', label: 'Buraco de Minhoca' },
    { id: 'limpeza_rapida_direita', icone: 'ph-arrow-right', label: 'Deslize Dir.' },
    { id: 'limpeza_rapida_esquerda', icone: 'ph-arrow-left', label: 'Deslize Esq.' },
    { id: 'limpeza_rapida_cima', icone: 'ph-arrow-up', label: 'Deslize Cima' },
    { id: 'limpeza_rapida_baixo', icone: 'ph-arrow-down', label: 'Deslize Baixo' },
    { id: 'balancar_direita', icone: 'ph-scales', label: 'Balançar Dir.' },
    { id: 'balancar_esquerda', icone: 'ph-scales', label: 'Balançar Esq.' },
    { id: 'rolagem_olho_de_peixe_direita', icone: 'ph-caret-right', label: 'Olho Peixe (Dir)' },
    { id: 'rolagem_olho_de_peixe_esquerda', icone: 'ph-caret-left', label: 'Olho Peixe (Esq)' },
    { id: 'rolagem_olho_de_peixe_cima', icone: 'ph-caret-up', label: 'Olho Peixe (Cima)' },
    { id: 'rolagem_olho_de_peixe_baixo', icone: 'ph-caret-down', label: 'Olho Peixe (Baixo)' },
    { id: 'rolagem_olho_de_peixe_cima_direita', icone: 'ph-arrow-up-right', label: 'Olho Peixe (C-Dir)' },
    { id: 'rolagem_olho_de_peixe_cima_esquerda', icone: 'ph-arrow-up-left', label: 'Olho Peixe (C-Esq)' },
    { id: 'rolagem_olho_de_peixe_baixo_direita', icone: 'ph-arrow-down-right', label: 'Olho Peixe (B-Dir)' },
    { id: 'rolagem_olho_de_peixe_baixo_esquerda', icone: 'ph-arrow-down-left', label: 'Olho Peixe (B-Esq)' },
    { id: 'nenhuma', icone: 'ph-scissors', label: 'Corte Seco' }
];

function pushHistory() {
    if(isUndoing || !projetoAtual) return;
    if(historyIndex < historyStack.length - 1) historyStack = historyStack.slice(0, historyIndex + 1);
    historyStack.push(JSON.parse(JSON.stringify(projetoAtual)));
    if(historyStack.length > 30) historyStack.shift(); else historyIndex++;
    salvarProjeto(); 
}

function undo() {
    if(historyIndex > 0) {
        isUndoing = true; historyIndex--;
        projetoAtual = JSON.parse(JSON.stringify(historyStack[historyIndex]));
        reconstruirDaMemoria(); salvarProjeto(); isUndoing = false;
    }
}

function redo() {
    if(historyIndex < historyStack.length - 1) {
        isUndoing = true; historyIndex++;
        projetoAtual = JSON.parse(JSON.stringify(historyStack[historyIndex]));
        reconstruirDaMemoria(); salvarProjeto(); isUndoing = false;
    }
}

document.addEventListener('keydown', function(e) {
    if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'textarea') return;

    if(e.ctrlKey && e.key === 'z') { e.preventDefault(); undo(); }
    else if((e.ctrlKey && e.key === 'y') || (e.ctrlKey && e.shiftKey && (e.key === 'Z' || e.key === 'z'))) { e.preventDefault(); redo(); }
    else if(e.key === 'Delete' || e.key === 'Del') {
        if(cenaAtivaPropriedades !== null && cenaAtivaPropriedades !== -1 && cenaAtivaPropriedades !== 'audio_locucao') { 
            if (typeof cenaAtivaPropriedades === 'string' && cenaAtivaPropriedades.startsWith('musica_')) {
                let idxMusica = parseInt(cenaAtivaPropriedades.split('_')[1]);
                removerMusicaSelecionada(idxMusica);
            } else {
                itemClicadoMenu = cenaAtivaPropriedades;
                removerCenaSelecionada(false); 
            }
        }
    }
});

async function salvarProjeto() {
    try {
        await fetch('/api/salvar_estado', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(projetoAtual) });
        let hint = document.getElementById('autoSaveHint');
        hint.style.opacity = '1'; setTimeout(() => { hint.style.opacity = '0'; }, 2000);
    } catch(e) {}
}

function reconstruirDaMemoria() {
    let tempoAtual = AudioEngine.obterTempoAtual();
    
    itemsDataset.clear();
    verificarECriarCamadas(); 

    let novos = [];
    
    projetoAtual.cenas.forEach((cena, index) => { 
        if(cena) {
            if (cena.foco_manual === undefined) cena.foco_manual = false;
            novos.push({ id: index, group: cena.camada, content: criarConteudoCena(index, cena.arquivo_origem), start: segToDate(cena.inicio), end: segToDate(cena.fim) }); 
        }
    });

    if(projetoAtual.volume_locucao === undefined) projetoAtual.volume_locucao = 1.0;
    novos.push({ 
        id: 'audio_locucao', group: 'a1', className: 'audio-clip', editable: false,
        start: segToDate(0), end: segToDate(projetoAtual.duracao),
        content: `
    <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
        <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
            <i class="ph-fill ph-music-notes"></i> ${faixa.titulo} // (ou ${titulo}, mantenha o que já estava no original)
        </div>
        <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none; display:flex; align-items:center; justify-content:center;">
            <div class="spinner-carregando" style="width:20px;height:20px;border-width:2px;border-top-color:#a855f7;"></div>
            <canvas class="waveform-music-canvas" data-idx="${index}" style="width: 100%; height: 100%; display: none;"></canvas>
        </div>
    </div>
`
    });

    if (projetoAtual.faixas_musicais) {
        projetoAtual.faixas_musicais.forEach((faixa, index) => {
            if (faixa) {
                novos.push({
                    id: `musica_${index}`, group: 'a2', className: 'music-clip',
                    content: `
                        <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                            <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                                <i class="ph-fill ph-music-notes"></i> ${faixa.titulo || 'Música'}
                            </div>
                            <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none;">
                                <canvas class="waveform-music-canvas" data-idx="${index}" style="width: 100%; height: 100%; display: block;"></canvas>
                            </div>
                        </div>
                    `,
                    start: segToDate(faixa.inicio), end: segToDate(faixa.fim),
                    editable: { updateTime: true, updateGroup: false, remove: false }
                });
            }
        });
    }

    itemsDataset.add(novos);
    carregarImagensNaMemoria(); sincronizarJSON(); renderCanvas(tempoAtual);
    
    if (cenaAtivaPropriedades === 'audio_locucao') {
        atualizarPainelAudio();
    } else if (cenaAtivaPropriedades !== -1 && projetoAtual.cenas[cenaAtivaPropriedades]) {
        atualizarPainel(cenaAtivaPropriedades);
    } else { 
        cenaAtivaPropriedades = -1; 
        document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`; 
    }
    
    // >>> FIX: A timeline pode demorar para renascer após um Ctrl+Z dependendo do PC. 
    // Então disparamos a pintura em 3 momentos diferentes para não ter erro!
    setTimeout(() => { if(window.desenharWaveform) window.desenharWaveform(); if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas(); }, 150);
    setTimeout(() => { if(window.desenharWaveform) window.desenharWaveform(); if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas(); }, 400);
    setTimeout(() => { if(window.desenharWaveform) window.desenharWaveform(); if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas(); }, 800);
}

const offCanvasA = document.createElement('canvas');
const offCanvasB = document.createElement('canvas');

function prioridadeCamada(camada) { 
    if (!camada) return 1;
    if (camada.startsWith('v')) {
        let num = parseInt(camada.replace('v', ''));
        return isNaN(num) ? 1 : num;
    }
    return 1; 
}

function verificarECriarCamadas() {
    if (!groupsDataset || !projetoAtual) return;
    
    let activeLayers = new Set([1]);
    
    if (projetoAtual.cenas) {
        projetoAtual.cenas.forEach(cena => {
            if (cena && cena.camada && cena.camada.startsWith('v')) {
                let num = parseInt(cena.camada.substring(1));
                if (!isNaN(num)) activeLayers.add(num);
            }
        });
    }
    
    let maxActive = Math.max(...Array.from(activeLayers));

    for (let i = 1; i <= maxActive; i++) {
        let gId = 'v' + i;
        if (!groupsDataset.get(gId)) {
            groupsDataset.add({
                id: gId,
                content: window.gerarCabecalhoCamada(gId, 'ph-fill ph-video-camera', `Vídeo ${i}`, 'inherit'),
                order: -i 
            });
        }
    }

    let existingGroups = groupsDataset.getIds().filter(id => typeof id === 'string' && id.startsWith('v'));
    existingGroups.forEach(id => {
        let num = parseInt(id.substring(1));
        if (num > maxActive) groupsDataset.remove(id);
    });
}

function achatarCamadasJS() {
    let brutas = projetoAtual.cenas.filter(c => c !== null); if (brutas.length === 0) return [];
    let pontosSet = new Set(); brutas.forEach(c => { pontosSet.add(c.inicio); pontosSet.add(c.fim); }); let pontosCorte = Array.from(pontosSet).sort((a, b) => a - b);
    let planificadas = []; let cenaAtual = null; let inicioAtual = 0.0;
    for (let i = 0; i < pontosCorte.length - 1; i++) {
        let t_inicio = pontosCorte[i]; let t_fim = pontosCorte[i + 1]; let meio = (t_inicio + t_fim) / 2.0; let vencedora = null; let maior_prio = -1;
        for (let c of brutas) { if (c.inicio <= meio && c.fim >= meio) { let prio = prioridadeCamada(c.camada || 'v1'); if (prio > maior_prio) { maior_prio = prio; vencedora = c; } } }
        if (vencedora === null) { vencedora = { id: -1, inicio: t_inicio, fim: t_fim, is_black: true }; }
        let diff = true; if (cenaAtual !== null) { if (cenaAtual.id === vencedora.id && cenaAtual.is_black === vencedora.is_black) diff = false; }
        if (diff) { if (cenaAtual !== null) { let novaCena = Object.assign({}, cenaAtual); novaCena.inicio = inicioAtual; novaCena.fim = t_inicio; if (novaCena.fim - novaCena.inicio > 0.03) planificadas.push(novaCena); } cenaAtual = vencedora; inicioAtual = t_inicio; }
    }
    if (cenaAtual !== null) { let novaCena = Object.assign({}, cenaAtual); novaCena.inicio = inicioAtual; novaCena.fim = pontosCorte[pontosCorte.length - 1]; if (novaCena.fim - novaCena.inicio > 0.03) planificadas.push(novaCena); }
    return planificadas;
}

const GLSL_FRAGMENTS = {
    'none': `#version 330\nuniform sampler2D tex_from;\nin vec2 uv; out vec4 f_color;\nvoid main() { f_color = texture(tex_from, uv); }`,
    'zoom_rotacao': `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nconst float PI = 3.14159265359;\nfloat easeInOutCubic(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }\nvec2 rotate_and_scale(vec2 p, float angle, float scale) { vec2 centered = p - 0.5; float s = sin(angle); float c = cos(angle); vec2 rotated = vec2(centered.x * c - centered.y * s, centered.x * s + centered.y * c); return (rotated / scale) + 0.5; }\nvoid main() {\nfloat ease = easeInOutCubic(progress);\nfloat angle_from = ease * -PI; float scale_from = 1.0 + ease * 4.0; \nvec2 uv_from = rotate_and_scale(uv, angle_from, scale_from);\nfloat angle_to = (ease - 1.0) * -PI; float scale_to = 1.0 + (1.0 - ease) * 4.0; \nvec2 uv_to = rotate_and_scale(uv, angle_to, scale_to);\nvec4 color_from = texture(tex_from, uv_from); vec4 color_to = texture(tex_to, uv_to);\nif(uv_from.x < 0.0 || uv_from.x > 1.0 || uv_from.y < 0.0 || uv_from.y > 1.0) color_from = vec4(0.0);\nif(uv_to.x < 0.0 || uv_to.x > 1.0 || uv_to.y < 0.0 || uv_to.y > 1.0) color_to = vec4(0.0);\nfloat mix_factor = smoothstep(0.4, 0.6, progress); f_color = mix(color_from, color_to, mix_factor);\n}`,
    'zoom_suave_paralaxe': `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nfloat easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }\nvec2 apply_spherical_bulge(vec2 p, float intensity) { vec2 d = p - 0.5; float dist = length(d); float radius = 1.0; if (dist > 0.0 && dist < radius) { float percent = dist / radius; float new_percent = pow(percent, 1.0 + intensity); return 0.5 + (d / percent) * new_percent * radius; } return p; }\nvoid main() {\nfloat ease = easeInOutQuint(progress);\nfloat bulge_from = ease * 3.0; vec2 uv_from = apply_spherical_bulge(uv, bulge_from); float zoom_A = mix(1.0, 0.02, ease); uv_from = 0.5 + (uv_from - 0.5) * zoom_A;\nfloat bulge_to = (1.0 - ease) * 3.0; vec2 uv_to = apply_spherical_bulge(uv, bulge_to); float zoom_B = mix(0.02, 1.0, ease); uv_to = 0.5 + (uv_to - 0.5) * zoom_B;\nvec4 color_from = texture(tex_from, uv_from); vec4 color_to = texture(tex_to, uv_to);\nif(uv_from.x < 0.0 || uv_from.x > 1.0 || uv_from.y < 0.0 || uv_from.y > 1.0) color_from = vec4(0.0); if(uv_to.x < 0.0 || uv_to.x > 1.0 || uv_to.y < 0.0 || uv_to.y > 1.0) color_to = vec4(0.0);\nfloat mix_factor = smoothstep(0.45, 0.55, progress); f_color = mix(color_from, color_to, mix_factor);\n}`,
    'warp_zoom': `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nfloat easeInOutQuart(float t) { return t < 0.5 ? 8.0 * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 4.0) / 2.0; }\nvec2 mirrored_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }\nvec4 warp_sample(sampler2D tex, vec2 p, float scale, float blur_strength) { vec2 center = vec2(0.5); vec2 dir = (p / scale + center * (1.0 - 1.0/scale)) - center; vec4 color = vec4(0.0); const int SAMPLES = 24; for (int i = 0; i < SAMPLES; i++) { float f = float(i) / float(SAMPLES - 1); vec2 shifted_uv = center + dir * (1.0 + f * blur_strength); color += texture(tex, mirrored_uv(shifted_uv)); } return color / float(SAMPLES); }\nvoid main() {\nfloat ease = easeInOutQuart(progress);\nfloat scale_A = mix(1.0, 12.0, ease); float blur_A = ease * 1.2; vec4 color_from = warp_sample(tex_from, uv, scale_A, blur_A);\nfloat scale_B = mix(0.01, 1.0, ease); float blur_B = (1.0 - ease) * 1.2; vec4 color_to = warp_sample(tex_to, uv, scale_B, blur_B);\nfloat mix_factor = smoothstep(0.4, 0.6, progress); f_color = mix(color_from, color_to, mix_factor);\n}`,
    'buraco_de_minhoca': `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nconst float PI = 3.14159265359;\nfloat hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }\nfloat easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }\nvec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }\nvoid main() {\nfloat ease = easeInOutQuint(progress);\nfloat peak_mask = sin(progress * PI); float shake_time = floor(progress * 150.0); vec2 shake = vec2(hash(vec2(shake_time, 1.0)), hash(vec2(shake_time, 2.0))) - 0.5; shake *= 0.15 * peak_mask; vec2 centerA = vec2(0.5) + shake; vec2 dirA = uv - centerA; float blur_strengthA = peak_mask * 1.2; float scaleA = mix(1.0, 25.0, ease);\nfloat pB = clamp((progress - 0.5) * 2.0, 0.0, 1.0); float easeOutB = 1.0 - pow(1.0 - pB, 5.0); vec2 centerB = vec2(0.5); vec2 dirB = uv - centerB; float r2 = dot(dirB, dirB); float concave_amount = mix(25.0, 0.0, easeOutB); vec2 distorted_dirB = dirB * (1.0 + concave_amount * r2); float scaleB = mix(0.03, 1.0, easeOutB); float blur_strengthB = mix(2.0, 0.0, easeOutB);\nfloat noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; float current_scaleA = scaleA * (1.0 + f * blur_strengthA); vec2 sampleA = centerA + dirA / current_scaleA; vec4 colA = texture(tex_from, wrap_uv(sampleA)); float current_scaleB = scaleB * (1.0 + f * blur_strengthB); vec2 sampleB = centerB + distorted_dirB / current_scaleB; vec4 colB = texture(tex_to, wrap_uv(sampleB)); color += mix(colA, colB, smoothstep(0.45, 0.55, progress)); }\nf_color = color / float(SAMPLES);\n}`
};

const FRAGMENT_OLHO_PEIXE = `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nconst float PI = 3.14159265359; const vec2 DIR = vec2({DIR_X}, {DIR_Y});\nfloat hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }\nfloat easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }\nvec2 apply_barrel(vec2 p, float amount) { vec2 d = (p - 0.5); float d_len = length(d); return 0.5 + (d * (1.0 + amount * (d_len * d_len))); }\nvec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }\nvoid main() {\nfloat ease = easeInOutQuint(progress); float bulge_amount = 2.5 * sin(progress * PI); vec2 distorted_uv = apply_barrel(uv, bulge_amount); vec2 offset = ease * 4.0 * DIR; float blur_mask = smoothstep(0.25, 0.45, progress) * (1.0 - smoothstep(0.55, 0.75, progress)); float blur_amount = blur_mask * 0.8; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 sample_uv = distorted_uv - offset + DIR * (f * blur_amount); color += mix(texture(tex_from, wrap_uv(sample_uv)), texture(tex_to, wrap_uv(sample_uv)), smoothstep(0.4, 0.6, progress)); } f_color = color / float(SAMPLES);\n}`;
const dirs_olho = {"rolagem_olho_de_peixe_baixo": [0.0, -1.0], "rolagem_olho_de_peixe_cima": [0.0, 1.0], "rolagem_olho_de_peixe_direita": [1.0, 0.0], "rolagem_olho_de_peixe_esquerda": [-1.0, 0.0], "rolagem_olho_de_peixe_baixo_direita": [1.0, -1.0], "rolagem_olho_de_peixe_baixo_esquerda": [-1.0, -1.0], "rolagem_olho_de_peixe_cima_direita": [1.0, 1.0], "rolagem_olho_de_peixe_cima_esquerda": [-1.0, 1.0]};
for (let nome in dirs_olho) { GLSL_FRAGMENTS[nome] = FRAGMENT_OLHO_PEIXE.replace("{DIR_X}", dirs_olho[nome][0].toFixed(1)).replace("{DIR_Y}", dirs_olho[nome][1].toFixed(1)); }

const FRAGMENT_LIMPEZA_RAPIDA = `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nconst float PI = 3.14159265359; const vec2 DIR = vec2({DIR_X}, {DIR_Y});\nfloat hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }\nfloat easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }\nvoid main() {\nfloat p = clamp((progress - 0.15) / 0.70, 0.0, 1.0); float ease = easeInOutQuint(p); vec2 offset = ease * DIR; float blur_amount = sin(p * PI) * 0.6; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 sample_uv = uv + DIR * (f * blur_amount); vec2 uvA = sample_uv - offset; vec2 uvB = uvA + DIR; bool inA = (uvA.x >= 0.0 && uvA.x <= 1.0 && uvA.y >= 0.0 && uvA.y <= 1.0); bool inB = (uvB.x >= 0.0 && uvB.x <= 1.0 && uvB.y >= 0.0 && uvB.y <= 1.0); color += (inA ? texture(tex_from, uvA) : vec4(0.0)) + (inB ? texture(tex_to, uvB) : vec4(0.0)); } f_color = color / float(SAMPLES);\n}`;
const dirs_limpeza = {"limpeza_rapida_direita": [1.0, 0.0], "limpeza_rapida_esquerda": [-1.0, 0.0], "limpeza_rapida_cima": [0.0, 1.0], "limpeza_rapida_baixo": [0.0, -1.0]};
for (let nome in dirs_limpeza) { GLSL_FRAGMENTS[nome] = FRAGMENT_LIMPEZA_RAPIDA.replace("{DIR_X}", dirs_limpeza[nome][0].toFixed(1)).replace("{DIR_Y}", dirs_limpeza[nome][1].toFixed(1)); }

const FRAGMENT_BALANCAR = `#version 330\nuniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;\nin vec2 uv; out vec4 f_color;\nconst float PI = 3.14159265359; const float DIR_X = {DIR_X};\nfloat hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }\nfloat easeInOutCubic(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }\nvec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }\nvoid main() {\nfloat ease = easeInOutCubic(progress); vec2 offset = vec2(ease * 2.0 * DIR_X, sin(progress * PI) * 0.25); float angle = sin(progress * PI) * 0.15 * DIR_X; float s = sin(angle); float c = cos(angle); float blur_mask = smoothstep(0.25, 0.45, progress) * (1.0 - smoothstep(0.55, 0.75, progress)); vec2 blur_vec = vec2(DIR_X, 0.2) * blur_mask * 0.15; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 p = uv - 0.5; p = vec2(p.x * c - p.y * s, p.x * s + p.y * c) + 0.5; vec2 sample_uv = p - offset + blur_vec * f; color += mix(texture(tex_from, wrap_uv(sample_uv)), texture(tex_to, wrap_uv(sample_uv)), smoothstep(0.4, 0.6, progress)); } f_color = color / float(SAMPLES);\n}`;
const dirs_balancar = {"balancar_direita": 1.0, "balancar_esquerda": -1.0};
for (let nome in dirs_balancar) { GLSL_FRAGMENTS[nome] = FRAGMENT_BALANCAR.replace(/{DIR_X}/g, dirs_balancar[nome].toFixed(1)); }

const WebGLRenderer = {
    gl: null, programs: {}, buffers: {}, textures: {},
    init: function(canvas) {
        this.gl = canvas.getContext('webgl2', { preserveDrawingBuffer: true });
        if (!this.gl) return; const gl = this.gl;
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        const vsSource = `#version 300 es\nin vec2 in_vert;\nin vec2 in_texcoord;\nout vec2 uv;\nvoid main() {\n  gl_Position = vec4(in_vert, 0.0, 1.0);\n  uv = in_texcoord;\n}`;
        const vs = gl.createShader(gl.VERTEX_SHADER); gl.shaderSource(vs, vsSource); gl.compileShader(vs);

        for (let name in GLSL_FRAGMENTS) {
            let fsSource = GLSL_FRAGMENTS[name].trim().replace('#version 330', '#version 300 es\nprecision highp float;');
            const fs = gl.createShader(gl.FRAGMENT_SHADER); gl.shaderSource(fs, fsSource); gl.compileShader(fs);
            const prog = gl.createProgram(); gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
            this.programs[name] = prog;
        }

        const vertices = new Float32Array([ -1.0, -1.0, 0.0, 0.0, 1.0, -1.0, 1.0, 0.0, -1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0 ]);
        this.buffers.quad = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.quad); gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
        this.textures.from = gl.createTexture(); this.setupTexture(this.textures.from);
        this.textures.to = gl.createTexture(); this.setupTexture(this.textures.to);
    },
    setupTexture: function(tex) {
        const gl = this.gl; gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    },
    render: function(transName, canvasA, canvasB, progress) {
        const gl = this.gl; if (!gl) return;
        gl.viewport(0, 0, gl.canvas.width, gl.canvas.height);
        let prog = this.programs[transName] || this.programs['none']; gl.useProgram(prog);
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.textures.from); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvasA); gl.uniform1i(gl.getUniformLocation(prog, "tex_from"), 0);
        if (canvasB) { gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.textures.to); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvasB); gl.uniform1i(gl.getUniformLocation(prog, "tex_to"), 1); }
        let locProgress = gl.getUniformLocation(prog, "progress"); if (locProgress) gl.uniform1f(locProgress, progress);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.quad);
        const posLoc = gl.getAttribLocation(prog, "in_vert"); gl.enableVertexAttribArray(posLoc); gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 16, 0);
        const texLoc = gl.getAttribLocation(prog, "in_texcoord"); gl.enableVertexAttribArray(texLoc); gl.vertexAttribPointer(texLoc, 2, gl.FLOAT, false, 16, 8);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
};

function getAnimacao(cena, idx) { if (cena.animacao && cena.animacao !== 'auto') return cena.animacao; if (cena.quadros_foco && cena.quadros_foco.length >= 5) return 'nenhuma'; const anims = ['zoom_in', 'zoom_out', 'pan']; return anims[idx % anims.length]; }
function getTransicao(cena, idx) { if (cena.transicao && cena.transicao !== 'auto') return cena.transicao; const transKeys = Object.keys(GLSL_FRAGMENTS).filter(k => k !== 'none'); return transKeys[idx % transKeys.length]; }

const AudioEngine = {
    ctx: new (window.AudioContext || window.webkitAudioContext)(), 
    masterBuffer: null, masterGain: null, 
    sfxBuffers: {}, bgmBuffers: {}, sources: [], 
    bgmGains: {}, sfxGains: [],
    startTime: 0, pauseTime: 0,
    mapaSFX: { 'zoom_rotacao': 'zoom_de_rotacao.mp3', 'zoom_suave_paralaxe': 'zoom_suave_paralaxe.mp3', 'warp_zoom': 'warp_zoom.mp3', 'buraco_de_minhoca': 'buraco_de_minhoca.mp3', 'limpeza_rapida_direita': 'limpeza_rapida_x.mp3', 'limpeza_rapida_esquerda': 'limpeza_rapida_x.mp3', 'limpeza_rapida_cima': 'limpeza_rapida_y.mp3', 'limpeza_rapida_baixo': 'limpeza_rapida_y.mp3', 'balancar_direita': 'balancar.mp3', 'balancar_esquerda': 'balancar.mp3', 'rolagem_olho_de_peixe_direita': 'rolagem_olho_de_peixe.mp3' },
    
    async carregarArquivo(url) { const response = await fetch(url); const arrayBuffer = await response.arrayBuffer(); return await this.ctx.decodeAudioData(arrayBuffer); },
    
    async inicializar() {
        try { this.masterBuffer = await this.carregarArquivo('/api/audio_mestre'); } catch(e) {}
        for (let key in this.mapaSFX) { try { this.sfxBuffers[key] = await this.carregarArquivo('/sfx/transicoes/' + this.mapaSFX[key]); } catch(e) {} }
        
        this.bgmBuffers = {};
        if (projetoAtual && projetoAtual.faixas_musicais) {
            for (let i = 0; i < projetoAtual.faixas_musicais.length; i++) {
                let faixa = projetoAtual.faixas_musicais[i];
                if (faixa && faixa.arquivo) {
                    try { this.bgmBuffers[i] = await this.carregarArquivo('/' + faixa.arquivo); } catch(e) {}
                }
            }
            setTimeout(window.desenharWaveformsMusicas, 500);
        }
        
        this.masterGain = this.ctx.createGain();
        this.masterGain.connect(this.ctx.destination);
    },
    tocar() {
        if (this.ctx.state === 'suspended') this.ctx.resume();
        this.pararTudo(); this.startTime = this.ctx.currentTime - this.pauseTime;
        this.bgmGains = {}; this.sfxGains = []; 
        
        if (this.masterBuffer) { 
            let source = this.ctx.createBufferSource(); 
            source.buffer = this.masterBuffer; 
            let multA1 = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas['a1'] !== undefined) ? projetoAtual.volumes_camadas['a1'] : 1.0;
            let gainVol = projetoAtual.volume_locucao !== undefined ? projetoAtual.volume_locucao : 1.0;
            this.masterGain.gain.value = gainVol * multA1;
            source.connect(this.masterGain); 
            source.start(0, this.pauseTime); 
            this.sources.push(source); 
        }

        if (projetoAtual.faixas_musicais) {
            projetoAtual.faixas_musicais.forEach((faixa, i) => {
                if (!faixa || !this.bgmBuffers[i]) return;
                
                if (faixa.fim > this.pauseTime) {
                    let source = this.ctx.createBufferSource();
                    source.buffer = this.bgmBuffers[i];
                    source.loop = true; 
                    
                    let gainNode = this.ctx.createGain();
                    let multA2 = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas['a2'] !== undefined) ? projetoAtual.volumes_camadas['a2'] : 1.0;
                    let vol = faixa.volume !== undefined ? faixa.volume : 0.15;
                    gainNode.gain.value = vol * multA2; 
                    
                    this.bgmGains[i] = gainNode; 
                    
                    source.connect(gainNode);
                    gainNode.connect(this.ctx.destination);
                    
                    let offsetNoArquivo = Math.max(0, this.pauseTime - faixa.inicio);
                    let tempoDeDisparo = this.ctx.currentTime + Math.max(0, faixa.inicio - this.pauseTime);
                    
                    source.start(tempoDeDisparo, offsetNoArquivo);
                    let duracaoFaltante = faixa.fim - Math.max(faixa.inicio, this.pauseTime);
                    source.stop(tempoDeDisparo + duracaoFaltante);
                    this.sources.push(source);
                }
            });
        }

        timelinePlanificada.forEach((cenaFlat, i) => {
            if (i >= timelinePlanificada.length - 1 || cenaFlat.is_black) return;
            let proximaCenaFlat = timelinePlanificada[i+1]; if (proximaCenaFlat.is_black) return;
            let rawA = projetoAtual.cenas[cenaFlat.id]; let transName = getTransicao(rawA, rawA.id);
            let audioKey = Object.keys(this.mapaSFX).find(k => transName.includes(k.replace('_direita','').replace('_esquerda','').replace('_cima','').replace('_baixo','')));
            if (!audioKey) audioKey = transName;
            if (transName !== 'nenhuma' && this.sfxBuffers[audioKey]) {
                let durTrans = Math.min(1.0, (cenaFlat.fim - cenaFlat.inicio) * 0.5, (proximaCenaFlat.fim - proximaCenaFlat.inicio) * 0.5);
                let sfxStartTime = cenaFlat.fim - durTrans;
                if (sfxStartTime >= this.pauseTime) {
                    let source = this.ctx.createBufferSource(); source.buffer = this.sfxBuffers[audioKey];
                    
                    // Lê o volume da transição e cruza com o volume Master da Camada de Vídeo
                    let multV = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas[rawA.camada] !== undefined) ? projetoAtual.volumes_camadas[rawA.camada] : 1.0;
                    let transVol = rawA.transition_volume !== undefined ? rawA.transition_volume : 1.0;
                    
                    let gainNode = this.ctx.createGain(); gainNode.gain.value = 0.20 * transVol * multV; 
                    source.connect(gainNode); gainNode.connect(this.ctx.destination);
                    source.start(this.ctx.currentTime + (sfxStartTime - this.pauseTime)); this.sources.push(source);
                    this.sfxGains.push({ layer: rawA.camada, node: gainNode, baseVol: 0.20 * transVol });
                }
            }
        });
    },
    pausar() { this.pauseTime = this.ctx.currentTime - this.startTime; this.pararTudo(); },
    buscar(tempo) { this.pauseTime = tempo; if (isPlaying) this.tocar(); },
    pararTudo() { this.sources.forEach(s => { try { s.stop(); } catch(e){} }); this.sources = []; },
    obterTempoAtual() { return isPlaying ? (this.ctx.currentTime - this.startTime) : this.pauseTime; }
};

window.desenharWaveform = function() {
    const canvas = document.querySelector('.waveform-canvas');
    if(!canvas || !AudioEngine.masterBuffer) return;
    const ctx = canvas.getContext('2d');
    
    const duracao = AudioEngine.masterBuffer.duration;
    canvas.width = Math.max(1000, Math.ceil(duracao * 100));
    canvas.height = 100;
    
    const width = canvas.width;
    const height = canvas.height;
    const data = AudioEngine.masterBuffer.getChannelData(0);
    const step = Math.ceil(data.length / width);
    const amp = height / 2;
    const multA1 = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas['a1'] !== undefined) ? projetoAtual.volumes_camadas['a1'] : 1.0;
    const gain = (projetoAtual.volume_locucao !== undefined ? projetoAtual.volume_locucao : 1.0) * multA1;

    ctx.clearRect(0, 0, width, height);
    
    ctx.fillStyle = 'rgba(16, 185, 129, 0.3)'; 
    ctx.fillRect(0, amp, width, 1);

    ctx.fillStyle = '#10b981'; 
    for(let i = 0; i < width; i++) {
        let min = 1.0, max = -1.0;
        let startIndex = i * step;
        for(let j = 0; j < step; j++) {
            let val = data[startIndex + j];
            if(val < min) min = val;
            if(val > max) max = val;
        }
        let peak = Math.max(Math.abs(min), Math.abs(max)) * gain;
        let y = amp - (peak * amp);
        let h = (peak * amp) * 2;
        ctx.fillRect(i, y, 1, Math.max(1, h));
    }
};

window.desenharWaveformsMusicas = function() {
    const canvases = document.querySelectorAll('.waveform-music-canvas');
    canvases.forEach(canvas => {
        let idx = parseInt(canvas.getAttribute('data-idx'));
        let faixa = projetoAtual.faixas_musicais[idx];
        let buffer = AudioEngine.bgmBuffers[idx];
        
        if(!buffer || !faixa) return;
        
        // INJEÇÃO: Esconde o spinner e mostra a onda desenhada
        let spinner = canvas.parentElement.querySelector('.spinner-carregando');
        if(spinner) spinner.style.display = 'none';
        canvas.style.display = 'block';
        
        const ctx = canvas.getContext('2d');
        const duracaoClipe = faixa.fim - faixa.inicio;
        
        canvas.width = Math.max(500, Math.ceil(duracaoClipe * 100)); 
        canvas.height = 100;
        
        const width = canvas.width;
        const height = canvas.height;
        const data = buffer.getChannelData(0);
        
        const amostrasPorSegundo = buffer.sampleRate;
        const totalSamples = duracaoClipe * amostrasPorSegundo;
        const step = totalSamples / width; 
        
        const amp = height / 2;
        const multA2 = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas['a2'] !== undefined) ? projetoAtual.volumes_camadas['a2'] : 1.0; const gain = (faixa.volume !== undefined ? faixa.volume : 0.15) * multA2;
        
        ctx.clearRect(0, 0, width, height);
        
        ctx.fillStyle = 'rgba(168, 85, 247, 0.4)'; 
        ctx.fillRect(0, amp, width, 1);

        ctx.fillStyle = 'rgba(168, 85, 247, 0.9)'; 
        for(let i = 0; i < width; i++) {
            let min = 1.0, max = -1.0;
            let startIndex = Math.floor(i * step);
            let endIndex = Math.floor((i + 1) * step);
            
            for(let j = startIndex; j < endIndex && j < data.length; j++) {
                let val = data[j];
                if(val < min) min = val;
                if(val > max) max = val;
            }
            
            let peak = Math.max(Math.abs(min), Math.abs(max)) * gain;
            let y = amp - (peak * amp);
            let h = (peak * amp) * 2;
            
            ctx.fillRect(i, y, 1, Math.max(1, h));
        }

        let pixelsPorSegundo = width / duracaoClipe;
        let fadeInPx = (faixa.fade_in || 0) * pixelsPorSegundo;
        let fadeOutPx = (faixa.fade_out || 0) * pixelsPorSegundo;
        
        const titleBarHeight = 18;
        
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)'; 
        
        if (fadeInPx > 0) {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.beginPath(); 
            ctx.moveTo(0, height); 
            ctx.lineTo(fadeInPx, titleBarHeight); 
            ctx.lineTo(0, titleBarHeight); 
            ctx.fill();
            
            ctx.beginPath(); 
            ctx.moveTo(0, height); 
            ctx.lineTo(fadeInPx, titleBarHeight); 
            ctx.stroke();
        }
        
        if (fadeOutPx > 0) {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.beginPath(); 
            ctx.moveTo(width - fadeOutPx, titleBarHeight); 
            ctx.lineTo(width, height); 
            ctx.lineTo(width, titleBarHeight); 
            ctx.fill();
            
            ctx.beginPath(); 
            ctx.moveTo(width - fadeOutPx, titleBarHeight); 
            ctx.lineTo(width, height); 
            ctx.stroke();
        }
    });
};

window.mudarVolumeAudio = function(val) {
    let gain = parseFloat(val);
    projetoAtual.volume_locucao = gain;
    if(AudioEngine.masterGain) AudioEngine.masterGain.gain.value = gain;
    
    let db = gain === 0 ? -60 : 20 * Math.log10(gain);
    document.getElementById('audioVolumeLabel').innerText = db.toFixed(1) + ' dB';
    desenharWaveform();
};

function atualizarPainelAudio() {
    let gain = projetoAtual.volume_locucao !== undefined ? projetoAtual.volume_locucao : 1.0;
    let db = gain === 0 ? -60 : 20 * Math.log10(gain);
    
    let html = `<div class="prop-header"><span>Faixa de Áudio</span><span>Locução</span></div>`; 
    html += `<div class="info-box">
        <label><i class="ph-fill ph-speaker-high"></i> Volume de Narração:</label>
        <div style="display:flex; align-items:center; gap: 10px; margin-top: 15px;">
            <input type="range" id="audioVolumeSlider" min="0" max="3" step="0.01" value="${gain}" 
                oninput="mudarVolumeAudio(this.value)" onchange="pushHistory()" style="flex: 1;">
            <span id="audioVolumeLabel" style="color:var(--primary-cyan); font-weight:bold; font-family:monospace; min-width:60px; text-align:right;">${db.toFixed(1)} dB</span>
        </div>
    </div>`;
    document.getElementById('painelProps').innerHTML = html;
}

function carregarImagensNaMemoria() {
    projetoAtual.cenas.forEach((cena, idx) => {
        if(!cena) { delete imageCache[idx]; return; }
        let expectedPath = cena.arquivo_origem ? `/proxy/preview/midia/${encodeURIComponent(cena.arquivo_origem)}` : `/proxy/preview/cena/${idx}`;
        if (imageCache[idx] && imageCache[idx]._srcPath === expectedPath) return; 
        
        let isVideo = cena.arquivo_origem && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(cena.arquivo_origem);

        if (isVideo) {
            const vid = document.createElement('video');
            vid.crossOrigin = "Anonymous";
            vid.playsInline = true;
            vid.volume = cena.volume_video !== undefined ? cena.volume_video : 1.0;
            vid.preload = "auto";
            vid._srcPath = expectedPath;
            
            vid.onseeked = () => { if (!isPlaying && !isPreviewing) renderCanvas(AudioEngine.obterTempoAtual()); };
            vid.onloadeddata = () => { if (!isPlaying && !isPreviewing) renderCanvas(AudioEngine.obterTempoAtual()); };
            
            // A trava de duração limpa e no lugar certo:
            vid.onloadedmetadata = () => { let d = vid.duration; if (d && d > 0) projetoAtual.cenas[idx].duracao_maxima = d; };
            
            vid.src = `${expectedPath}?t=${Date.now()}`;
            vid.load();
            imageCache[idx] = vid;
        } else {
            const img = new Image(); 
            img.crossOrigin = "Anonymous";
            img._srcPath = expectedPath; 
            img.onload = () => { if (!isPlaying && !isPreviewing) renderCanvas(AudioEngine.obterTempoAtual()); };
            img.src = `${expectedPath}?t=${Date.now()}`;
            imageCache[idx] = img;
        }
    });
}

function segToDate(seg) { return new Date(2000, 0, 1, 0, 0, seg, (seg % 1) * 1000); }
function dateToSeg(date) { return date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds() + date.getMilliseconds() / 1000; }
function formatTime(segundos) { let min = Math.floor(segundos / 60); let sec = Math.floor(segundos % 60); let dec = Math.floor((segundos % 1) * 10); return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}.${dec}`; }
function formatTimeNormal(segundos) { let min = Math.floor(segundos / 60); let sec = Math.floor(segundos % 60); return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`; }

function criarConteudoCena(id, arquivo_origem) {
    let caminhoBase = arquivo_origem ? `/proxy/thumb/midia/${encodeURIComponent(arquivo_origem)}` : `/proxy/thumb/cena/${id}`;
    let isVideo = arquivo_origem && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(arquivo_origem);
    
    let iconeFita = isVideo ? '<i class="ph-fill ph-film-strip" style="margin-right: 4px; color: var(--primary-cyan);"></i>' : '';

    return `
        <div style="width: 100%; height: 100%; display: flex; flex-direction: row; align-items:center; box-sizing: border-box; overflow: hidden; background: transparent;">
            <div style="font-size: 11px; font-weight: 600; background: transparent; color: white; border-right: 1px solid rgba(255,255,255,0.1); flex-shrink: 0; padding: 0 8px; z-index: 2; height: 100%; display:flex; align-items:center; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                ${iconeFita} Cena ${id+1}
            </div>
            <div style="flex-grow: 1; height: 100%; position: relative;">
                <img src="${caminhoBase}?t=${Date.now()}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.8;" onerror="if(!this.dataset.retry){ this.dataset.retry='1'; let img=this; setTimeout(function(){ img.src='${caminhoBase}?retry=' + Date.now(); }, 1200); } else { this.style.display='none'; }">
            </div>
        </div>
    `;
}

// --- MOTOES DE ÁUDIO DA BIBLIOTECA ---
let playerHoverBib = new Audio();

window.tocarPreviewAudioBib = function(caminho) {
    playerHoverBib.src = "/" + caminho;
    playerHoverBib.play().catch(e => {});
};

window.pararPreviewAudioBib = function() {
    playerHoverBib.pause();
    playerHoverBib.currentTime = 0;
};

window.criarItemAudioBiblioteca = function(caminho, titulo) {
    let safePath = caminho.replace(/'/g, "\\'").replace(/"/g, "&quot;");
    let safeTitle = titulo.replace(/'/g, "\\'").replace(/"/g, "&quot;");
    
    return `
    <div class="item-midia audio" title="${safeTitle}" 
         onmouseenter="tocarPreviewAudioBib('${safePath}')" 
         onmouseleave="pararPreviewAudioBib()">
        
        <div class="audio-title-bar">
            <i class="ph-fill ph-music-notes" style="color: var(--primary-purple);"></i>
            <div class="marquee-wrapper">
                <span class="marquee-text">${safeTitle}</span>
            </div>
        </div>
        
        <i class="ph-fill ph-waveform audio-icon-bg"></i>
        <canvas class="canvas-onda-bib" data-caminho="${safePath}"></canvas>
        
        <button class="btn-add-agulha" onclick="inserirAudioNaTimeline('${safePath}', '${safeTitle}')"><i class="ph ph-plus"></i></button>
    </div>`;
};

window.inserirAudioNaTimeline = function(caminho, titulo) {
    if (!projetoAtual.faixas_musicais) projetoAtual.faixas_musicais = [];
    
    let tempoAgulha = dateToSeg(timeline.getCustomTime('agulha'));
    let novoIndex = projetoAtual.faixas_musicais.length;
    
    let novaFaixa = { arquivo: caminho, titulo: titulo, clima: 'Biblioteca', inicio: tempoAgulha, fim: tempoAgulha + 10.0, volume: 0.15, fade_in: 1.5, fade_out: 1.5 };
    projetoAtual.faixas_musicais.push(novaFaixa);
    
    itemsDataset.add({
        id: `musica_${novoIndex}`, group: 'a2', className: 'music-clip',
        content: `
            <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                    <i class="ph-fill ph-music-notes"></i> ${titulo}
                </div>
                <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none;">
                    <canvas class="waveform-music-canvas" data-idx="${novoIndex}" style="width: 100%; height: 100%; display: block;"></canvas>
                </div>
            </div>
        `,
        start: segToDate(novaFaixa.inicio), end: segToDate(novaFaixa.fim),
        editable: { updateTime: true, updateGroup: false, remove: false }
    });
    sincronizarJSON(); pushHistory(); AudioEngine.inicializar();
};

window.desenharOndasBiblioteca = async function() {
    const canvases = document.querySelectorAll('.canvas-onda-bib:not([data-desenhado="true"])');
    for (let canvas of canvases) {
        let caminho = canvas.getAttribute('data-caminho');
        try {
            let response = await fetch("/" + caminho);
            let arrayBuffer = await response.arrayBuffer();
            let audioBuffer = await AudioEngine.ctx.decodeAudioData(arrayBuffer);
            
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.offsetWidth || 100;
            canvas.height = canvas.offsetHeight || 40;
            const data = audioBuffer.getChannelData(0);
            const step = Math.ceil(data.length / canvas.width);
            const amp = canvas.height / 2;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#a855f7'; 
            
            for(let i = 0; i < canvas.width; i++) {
                let min = 1.0, max = -1.0;
                let startIndex = i * step;
                for(let j = 0; j < step && (startIndex + j) < data.length; j++) {
                    let val = data[startIndex + j];
                    if(val < min) min = val; if(val > max) max = val;
                }
                let peak = Math.max(Math.abs(min), Math.abs(max));
                let h = (peak * amp) * 2;
                ctx.fillRect(i, amp - (peak * amp), 1, Math.max(1, h));
            }
            canvas.dataset.desenhado = "true";
        } catch(e) {}
    }
};
// ---------------------------------------------

async function carregarBiblioteca() {
    try {
        const res = await fetch('/api/biblioteca'); 
        const data = await res.json(); 
        let html = '';
        
        let audiosNoProjeto = new Set();
        let htmlAudios = '';

        // 1. Extrai as músicas que já estão no Projeto Atual (Timeline)
        if (projetoAtual && projetoAtual.faixas_musicais) {
            projetoAtual.faixas_musicais.forEach((faixa) => {
                if (faixa && faixa.arquivo && !audiosNoProjeto.has(faixa.arquivo)) {
                    audiosNoProjeto.add(faixa.arquivo);
                    htmlAudios += window.criarItemAudioBiblioteca(faixa.arquivo, faixa.titulo || "Faixa de Áudio");
                }
            });
        }

        // 2. Extrai imagens, vídeos e novos áudios importados
        if(data.importadas && data.importadas.length > 0) {
            let htmlVisuais = '';
            data.importadas.forEach(f => { 
                let isVideo = /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(f);
                let isAudio = /\.(mp3|wav|ogg|m4a|aac)$/i.test(f);
                
                if (isAudio) {
                    if (!audiosNoProjeto.has(f)) {
                        audiosNoProjeto.add(f);
                        let nomeLimpo = f.split('/').pop().replace(/\.(mp3|wav|ogg|m4a|aac)$/i, '');
                        htmlAudios += window.criarItemAudioBiblioteca(f, nomeLimpo);
                    }
                } else {
                    let badgeVideo = isVideo ? `<div style="position:absolute; top:4px; left:4px; background:rgba(0,0,0,0.7); padding:2px 4px; border-radius:4px; font-size:10px;"><i class="ph-fill ph-video-camera"></i></div>` : '';
                    htmlVisuais += `
                    <div class="item-midia" title="${f}">
                        <img src="/proxy/thumb/midia/${encodeURIComponent(f)}?t=${Date.now()}" style="width:100%; height:100%; object-fit:cover;">
                        ${badgeVideo}
                        <button class="btn-add-agulha" onclick="inserirMidiaNaTimeline('${f}')"><i class="ph ph-plus"></i></button>
                    </div>`; 
                }
            });
            if (htmlVisuais !== '') {
                html += `<div class="sub-header-lib">Mídias Importadas</div>` + htmlVisuais;
            }
        }

        // 3. Monta a seção de Áudios
        if (htmlAudios !== '') {
            html += `<div class="sub-header-lib"><i class="ph-fill ph-music-notes"></i> Áudios do Projeto</div>` + htmlAudios;
        }

        // 4. Extrai as Mídias Geradas por IA
        if(data.geradas && data.geradas.length > 0) {
            html += `<div class="sub-header-lib"><i class="ph-fill ph-magic-wand"></i> Geradas pela IA</div>`;
            data.geradas.forEach((f, i) => { html += `<div class="item-midia" title="Cena Padrão ${i+1}"><img src="/proxy/thumb/cena/${i}?t=${Date.now()}"><button class="btn-add-agulha" onclick="inserirMidiaNaTimeline(null, ${i})"><i class="ph ph-plus"></i></button></div>`; });
        }
        
        document.getElementById('containerBiblioteca').innerHTML = `<div class="lista-midias">${html}</div>`;
        
        // Manda o motor decodificar e pintar os gráficos de onda das músicas recém-criadas
        setTimeout(window.desenharOndasBiblioteca, 400);
    } catch (e) {}
}

async function inicializar() {
    const resposta = await fetch('/api/dados_projeto');
    projetoAtual = await resposta.json();
    
    await AudioEngine.inicializar();
    carregarImagensNaMemoria();
    carregarBiblioteca();

    const mainCanvas = document.getElementById('previewCanvas');
    let isVertical = false; let form = (projetoAtual.formato || "").toLowerCase();
    if (form.includes('short') || form === 'vertical' || form === 'tiktok') isVertical = true;
    if (projetoAtual.resolucao && projetoAtual.resolucao[0] < projetoAtual.resolucao[1]) isVertical = true;

    if (isVertical) { mainCanvas.width = 1080; mainCanvas.height = 1920; mainCanvas.style.aspectRatio = "9/16"; mainCanvas.style.height = "100%"; mainCanvas.style.width = "auto"; } 
    else { mainCanvas.width = 1920; mainCanvas.height = 1080; mainCanvas.style.aspectRatio = "16/9"; mainCanvas.style.width = "100%"; mainCanvas.style.height = "auto"; }

    offCanvasA.width = mainCanvas.width; offCanvasA.height = mainCanvas.height; offCanvasB.width = mainCanvas.width; offCanvasB.height = mainCanvas.height;
    WebGLRenderer.init(mainCanvas);

    const container = document.getElementById('timeline');
    itemsDataset = new vis.DataSet();
    
    projetoAtual.cenas.forEach((cena, index) => { 
        if(cena) { 
            cena.id = index; 
            if (cena.foco_manual === undefined) cena.foco_manual = false;
            itemsDataset.add({ id: index, group: cena.camada || 'v1', content: criarConteudoCena(index, cena.arquivo_origem), start: segToDate(cena.inicio), end: segToDate(cena.fim) }); 
        } 
    });

    if(projetoAtual.volume_locucao === undefined) projetoAtual.volume_locucao = 1.0;
    itemsDataset.add({ 
        id: 'audio_locucao', group: 'a1', className: 'audio-clip', editable: false,
        start: segToDate(0), end: segToDate(projetoAtual.duracao),
        content: `
            <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; display: flex; align-items: center; gap: 5px;">
                    <i class="ph-fill ph-waveform"></i> Faixa de Narração
                </div>
                <div class="waveform-container">
                    <canvas class="waveform-canvas"></canvas>
                </div>
            </div>
        `
    });

    if (projetoAtual.faixas_musicais) {
        let novasMusicas = [];
        projetoAtual.faixas_musicais.forEach((faixa, index) => {
            if (faixa) {
                novasMusicas.push({
                    id: `musica_${index}`, group: 'a2', className: 'music-clip',
                    content: `
                        <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                            <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                                <i class="ph-fill ph-music-notes"></i> ${faixa.titulo || 'Música'}
                            </div>
                            <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none;">
                                <canvas class="waveform-music-canvas" data-idx="${index}" style="width: 100%; height: 100%; display: block;"></canvas>
                            </div>
                        </div>
                    `,
                    start: segToDate(faixa.inicio), end: segToDate(faixa.fim),
                    editable: { updateTime: true, updateGroup: false, remove: false }
                });
            }
        });
        itemsDataset.add(novasMusicas);
    }

    sincronizarJSON(); 

    groupsDataset = new vis.DataSet([
        {id: 'a2', content: window.gerarCabecalhoCamada('a2', 'ph-fill ph-music-notes', 'Trilha Sonora', '#a855f7'), order: 100},
        {id: 'a1', content: window.gerarCabecalhoCamada('a1', 'ph-fill ph-microphone-stage', 'Locução', '#10b981'), order: 200}
    ]);
    
    verificarECriarCamadas(); 
    
    const options = { 
        start: segToDate(0), 
        end: segToDate(projetoAtual.duracao), 
        stack: false, 
        height: '100%', 
        width: '100%', 
        margin: { item: 0, axis: 0 }, 
        min: segToDate(0), 
        showMajorLabels: false, 
        showMinorLabels: false,
        editable: { add: false, remove: false, updateTime: true, updateGroup: true }, 
        groupOrder: 'order',
        
        snap: function (date, clone, id) { 
            let seg = dateToSeg(date);
            if (seg <= 0.2) return segToDate(0);
            return date; 
        }, 
        xss: { disabled: true }, 
        verticalScroll: true, 
        zoomKey: 'ctrlKey',   
        horizontalScroll: true, 

        onMoving: function (item, callback) {
            if (!window.isShiftPressed) { callback(item); return; }
            let snapThreshold = 0.4;
            let snapPoints = [0]; 
            itemsDataset.get().forEach(i => {
                if (i.id !== item.id) {
                    snapPoints.push(dateToSeg(i.start));
                    snapPoints.push(dateToSeg(i.end));
                }
            });
            if (timeline) {
                snapPoints.push(dateToSeg(timeline.getCustomTime('agulha')));
            }
            let itemStartSec = dateToSeg(item.start);
            let itemEndSec = dateToSeg(item.end);
            let duration = itemEndSec - itemStartSec;
            let closestStart = snapPoints.reduce((prev, curr) => Math.abs(curr - itemStartSec) < Math.abs(prev - itemStartSec) ? curr : prev);
            let closestEnd = snapPoints.reduce((prev, curr) => Math.abs(curr - itemEndSec) < Math.abs(prev - itemEndSec) ? curr : prev);
            let distStart = Math.abs(closestStart - itemStartSec);
            let distEnd = Math.abs(closestEnd - itemEndSec);
            let oldItem = itemsDataset.get(item.id);
            let oldStartSec = dateToSeg(oldItem.start);
            let oldEndSec = dateToSeg(oldItem.end);
            let isResizingStart = Math.abs(itemStartSec - oldStartSec) > 0.001 && Math.abs(itemEndSec - oldEndSec) < 0.001;
            let isResizingEnd = Math.abs(itemEndSec - oldEndSec) > 0.001 && Math.abs(itemStartSec - oldStartSec) < 0.001;
            let isMoving = !isResizingStart && !isResizingEnd;

            if (isResizingStart) {
                if (distStart < snapThreshold) itemStartSec = closestStart;
            } else if (isResizingEnd) {
                if (distEnd < snapThreshold) itemEndSec = closestEnd;
            } else if (isMoving) {
                if (distStart < snapThreshold && distStart <= distEnd) {
                    itemStartSec = closestStart; itemEndSec = closestStart + duration;
                } else if (distEnd < snapThreshold) {
                    itemEndSec = closestEnd; itemStartSec = closestEnd - duration;
                }
            }
            if (itemEndSec - itemStartSec < 0.1) { itemStartSec = oldStartSec; itemEndSec = oldEndSec; }
            
            // >>> A PAREDE DE CONCRETO (AGORA À PROVA DO ÍMÃ) <<<
            let idxMedia = parseInt(item.id);
            if (!isNaN(idxMedia) && projetoAtual.cenas[idxMedia]) {
                let cenaRef = projetoAtual.cenas[idxMedia];
                let isVid = cenaRef.arquivo_origem && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(cenaRef.arquivo_origem);
                
                if (isVid) {
                    let maxDur = cenaRef.duracao_maxima;
                    if (!maxDur && imageCache[idxMedia] && imageCache[idxMedia].duration) {
                        maxDur = imageCache[idxMedia].duration;
                        cenaRef.duracao_maxima = maxDur; // Salva para uso futuro
                    }
                    
                    if (maxDur && !isNaN(maxDur)) {
                        let novaDuracao = itemEndSec - itemStartSec;
                        // Tolera uma flutuação minúscula do processador
                        if (novaDuracao > maxDur + 0.005) {
                            // Mede quem sofreu a maior alteração bruta
                            let deltaEsq = Math.abs(itemStartSec - oldStartSec);
                            let deltaDir = Math.abs(itemEndSec - oldEndSec);
                            
                            if (deltaEsq > deltaDir) {
                                itemStartSec = itemEndSec - maxDur; // Puxou a esquerda
                            } else {
                                itemEndSec = itemStartSec + maxDur; // Puxou a direita
                            }
                        }
                    }
                }
            }

            item.start = segToDate(itemStartSec); item.end = segToDate(itemEndSec);
            callback(item);
        },

        onMove: function (item, callback) { 
            if (typeof item.id === 'string' && item.id.startsWith('musica_')) {
                let idx = parseInt(item.id.split('_')[1]);
                projetoAtual.faixas_musicais[idx].inicio = dateToSeg(item.start);
                projetoAtual.faixas_musicais[idx].fim = dateToSeg(item.end);
                
                let faixas = projetoAtual.faixas_musicais;
                let validas = faixas.map((f, i) => ({f: f, idx: i})).filter(x => x.f).sort((a, b) => a.f.inicio - b.f.inicio);
                
                for(let k=0; k < validas.length - 1; k++) {
                    let atual = validas[k]; let prox = validas[k+1];
                    let overlap = atual.f.fim - prox.f.inicio;
                    if (overlap > 0) { atual.f.fade_out = overlap; prox.f.fade_in = overlap; } 
                    else { atual.f.fade_out = 0; prox.f.fade_in = 0; }
                }
                sincronizarJSON(); pushHistory();
                if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas();
                if (typeof window.atualizarPainelMusica === 'function' && cenaAtivaPropriedades !== -1 && typeof cenaAtivaPropriedades === 'string' && cenaAtivaPropriedades.startsWith('musica_')) {
                    let currentPanelIdx = parseInt(cenaAtivaPropriedades.split('_')[1]);
                    window.atualizarPainelMusica(currentPanelIdx);
                }
                callback(item); return;
            } else {
                let itemStartSec = dateToSeg(item.start);
                let itemEndSec = dateToSeg(item.end);
                let novaCamadaNum = 1;

                while (true) {
                    let groupId = 'v' + novaCamadaNum;
                    let colisoes = itemsDataset.get({ filter: function (outro) { 
                        if (outro.id === item.id || outro.group !== groupId) return false;
                        let outroStart = dateToSeg(outro.start);
                        let outroEnd = dateToSeg(outro.end);
                        return (itemStartSec < outroEnd - 0.05) && (itemEndSec > outroStart + 0.05); 
                    }}); 
                    
                    if (colisoes.length === 0) {
                        item.group = groupId; 
                        break;
                    }
                    novaCamadaNum++; 
                } 
                
                if (!groupsDataset.get(item.group)) {
                    groupsDataset.add({
                        id: item.group,
                        content: window.gerarCabecalhoCamada(item.group, 'ph-fill ph-video-camera', `Vídeo ${novaCamadaNum}`, 'inherit'),
                        order: -novaCamadaNum
                    });
                }

                let idx = parseInt(item.id);
                
                // >>> TRAVA FINAL DE SEGURANÇA NA SOLTURA DO MOUSE <<<
                let cenaRef = projetoAtual.cenas[idx];
                let isVid = cenaRef.arquivo_origem && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(cenaRef.arquivo_origem);
                if (isVid) {
                    let maxDur = cenaRef.duracao_maxima || (imageCache[idx] ? imageCache[idx].duration : null);
                    if (maxDur && (itemEndSec - itemStartSec > maxDur + 0.005)) {
                        itemEndSec = itemStartSec + maxDur;
                        item.end = segToDate(itemEndSec); // Corta visualmente
                    }
                }

                projetoAtual.cenas[idx].inicio = itemStartSec;
                projetoAtual.cenas[idx].fim = itemEndSec;
                projetoAtual.cenas[idx].camada = item.group;

                callback(item); 
                verificarECriarCamadas(); 
                sincronizarJSON(); 
                pushHistory(); 
                renderCanvas(AudioEngine.obterTempoAtual()); 
            }
        } 
    };

    timeline = new vis.Timeline(container, itemsDataset, groupsDataset, options); 
    timeline.addCustomTime(segToDate(0), 'agulha');

    let bloquearCliqueFantasma = false;

    timeline.on('timechange', function (props) { 
        if (props.id === 'agulha') { 
            bloquearCliqueFantasma = true; 
            if (isPlaying) togglePlay(); 
            
            let dataZero = segToDate(0);
            let msZero = (dataZero instanceof Date) ? dataZero.getTime() : new Date(dataZero).getTime();
            let msArrastado = props.time.getTime();

            if (msArrastado <= msZero + 200) { 
                props.time = new Date(msZero); 
            }

            let seg = dateToSeg(props.time);
            
            if (seg > projetoAtual.duracao) {
                seg = projetoAtual.duracao;
                let dataFim = segToDate(seg);
                props.time = new Date((dataFim instanceof Date) ? dataFim.getTime() : new Date(dataFim).getTime());
            }
            
            AudioEngine.pauseTime = seg;
            atualizarMostradorTempo(seg);
            renderCanvas(seg);
        } 
    }); 

    timeline.on('timechanged', function (props) {
        if (props.id === 'agulha') {
            let dataZero = segToDate(0);
            let msZero = (dataZero instanceof Date) ? dataZero.getTime() : new Date(dataZero).getTime();

            if (props.time.getTime() <= msZero + 200) { 
                props.time = new Date(msZero); 
            }

            let seg = dateToSeg(props.time);
            if (seg > projetoAtual.duracao) seg = projetoAtual.duracao;

            buscarTempo(seg); 
            
            bloquearCliqueFantasma = true;
            setTimeout(() => { bloquearCliqueFantasma = false; }, 200);
        }
    });

    timeline.on('click', function (props) { 
        if (bloquearCliqueFantasma) return; 
        
        // A verdadeira muralha: verifica no HTML puro se o clique nasceu dentro do painel esquerdo
        let clicouNoPainel = props.event && props.event.target && props.event.target.closest('.vis-left');
        
        // Move a agulha apenas se NÃO foi no painel esquerdo e NÃO foi na própria agulha
        if (!clicouNoPainel && props.time && props.what !== 'custom-time') { 
            buscarTempo(dateToSeg(props.time)); 
        } 
    }); 
    
    let pulsos = 0;
    let resgateTimeline = setInterval(() => {
        if (timeline) {
            window.dispatchEvent(new Event('resize'));
            if (typeof timeline.checkResize === 'function') timeline.checkResize();
            if (typeof timeline.redraw === 'function') timeline.redraw();
            
            // >>> FIX: Metralhadora de pintura! Garante que as ondas sejam desenhadas 
            // no exato milissegundo em que as caixinhas surgirem no HTML.
            if (window.desenharWaveform) window.desenharWaveform();
            if (window.desenharWaveformsMusicas) window.desenharWaveformsMusicas();
        }
        pulsos++;
        if (pulsos > 20) clearInterval(resgateTimeline); // 2 segundos de insistência garantida
    }, 100);
    
    timeline.on('select', function (props) { 
        if (props.items.length > 0) {
            itemClicadoMenu = props.items[0]; 
            
            if(itemClicadoMenu === 'audio_locucao') { 
                cenaAtivaPropriedades = 'audio_locucao'; 
                atualizarPainelAudio(); 
            } 
            else if (typeof itemClicadoMenu === 'string' && itemClicadoMenu.startsWith('musica_')) {
                cenaAtivaPropriedades = itemClicadoMenu;
                let idxMusica = parseInt(itemClicadoMenu.split('_')[1]);
                window.atualizarPainelMusica(idxMusica);
            }
            else { 
                cenaAtivaPropriedades = itemClicadoMenu;
                atualizarPainel(props.items[0]); 
            }
        } else { 
            itemClicadoMenu = null; 
            cenaAtivaPropriedades = -1;
            document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`; 
        }
    });
    
    document.addEventListener('click', (e) => { 
        document.getElementById('menuContexto').style.display = 'none'; 
        if (!e.target.closest('.custom-select')) { document.querySelectorAll('.select-items').forEach(el => el.classList.remove('select-show')); }
    }); 
    
    document.getElementById('timeline').addEventListener('contextmenu', function (e) { 
        e.preventDefault(); 
        let props = timeline.getEventProperties(e); 
        const menu = document.getElementById('menuContexto'); 
        let htmlMenu = '';

        if (props.item === null && props.group === 'a2') {
            htmlMenu = `
                <ul>
                    <li onclick="abrirModalNovaMusica(); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-plus-circle"></i> Adicionar Nova Música</li>
                    <li class="divisor"></li>
                    <li class="danger" onclick="removerTodasMusicas(); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-trash"></i> Remover Todas as Músicas</li>
                </ul>
            `;
        } 
        else if (props.item === null && props.group && props.group.startsWith('v')) {
            htmlMenu = `
                <ul>
                    <li onclick="window.camadaAlvoNovaCena = '${props.group}'; document.getElementById('fileUploadTimeline').click(); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-video-camera"></i> Adicionar Nova Mídia</li>
                    <li class="divisor"></li>
                    <li class="danger" onclick="removerTodasCenas(); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-trash"></i> Remover Todas as Mídias</li>
                </ul>
            `;
        }
        else if (props.item !== null && props.item !== 'audio_locucao') { 
            itemClicadoMenu = props.item; 

            if (typeof itemClicadoMenu === 'string' && itemClicadoMenu.startsWith('musica_')) {
                let idxMusica = parseInt(itemClicadoMenu.split('_')[1]);
                htmlMenu = `
                    <ul>
                        <li onclick="abrirModalSubstituirMusica(${idxMusica}); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-music-notes"></i> Substituir Áudio</li>
                        <li class="divisor"></li>
                        <li class="danger" onclick="removerMusicaSelecionada(${idxMusica}); document.getElementById('menuContexto').style.display='none';"><i class="ph ph-trash"></i> Remover Faixa</li>
                    </ul>
                `;
            } else {
                htmlMenu = `
                    <ul>
                        <li onclick="acionarIAFocal()"><i class="ph ph-robot"></i> Detectar Ponto Focal (IA)</li>
                        <li onclick="abrirModalFoco()"><i class="ph ph-crosshair"></i> Escolher Ponto Manualmente</li>
                        <li class="divisor"></li>
                        <li onclick="acionarSubstituicao()"><i class="ph ph-arrows-clockwise"></i> Substituir Mídia</li>
                        <li onclick="acionarUpscaleCena()"><i class="ph ph-sparkle" style="color:var(--primary-purple);"></i> Melhorar Mídia (IA)</li>
                        <li class="divisor"></li>
                        <li class="danger" onclick="removerCenaSelecionada(true)"><i class="ph ph-trash"></i> Remover Cena</li>
                    </ul>
                `;
            }
        } 

        if (htmlMenu !== '') {
            menu.innerHTML = htmlMenu;
            menu.style.display = 'block'; 
            let posX = e.pageX;
            let posY = e.pageY;
            if (posX + menu.offsetWidth > window.innerWidth) posX = window.innerWidth - menu.offsetWidth - 10;
            if (posY + menu.offsetHeight > window.innerHeight) posY = window.innerHeight - menu.offsetHeight - 10;
            menu.style.left = posX + 'px'; 
            menu.style.top = posY + 'px';
        } else {
            menu.style.display = 'none';
        }
    });

    // ATUALIZAÇÕES BLINDADAS APÓS A CRIAÇÃO DA TIMELINE
    atualizarMostradorTempo(0); 

    // Destrói o modal primeiro, para que o fluxo do DOM não seja bloqueado
    const loadingScreen = document.getElementById('telaCarregamento');
    if (loadingScreen) {
        loadingScreen.style.opacity = '0';
        setTimeout(() => {
            loadingScreen.style.display = 'none';
            // Renderiza apenas após o modal sair do caminho
            if (timeline && typeof timeline.redraw === 'function') {
                timeline.checkResize(); 
                timeline.redraw();
            }
            renderCanvas(0); 
            setTimeout(desenharWaveform, 200); 
            pushHistory();
        }, 400); 
    } else {
        renderCanvas(0); 
        setTimeout(desenharWaveform, 200); 
        pushHistory();
    }
}

function calculateEasedProgress(p, start, end, easing) {
    if (p <= start) return 0.0;
    if (p >= end) return 1.0;
    let t = (p - start) / (end - start);
    
    if (easing === 'suave') {
        return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    } else if (easing === 'dinamica') {
        const c1 = 1.70158;
        const c3 = c1 + 1;
        return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    }
    return t; 
}

function renderizarCenaBase(ctxAlvo, canvasRef, cenaRaw, img, t_local, duracao_cena) {
    let isVideo = img instanceof HTMLVideoElement;
    
    if (!img || (!isVideo && !img.complete) || (isVideo && img.readyState < 2)) { 
        ctxAlvo.fillStyle = '#000000'; ctxAlvo.fillRect(0, 0, canvasRef.width, canvasRef.height); return; 
    }

    if (isVideo) {
        let tempoAlvo = Math.min(t_local, img.duration || 999);
        let baseVol = cenaRaw.volume_video !== undefined ? cenaRaw.volume_video : 1.0;
        let multV = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas[cenaRaw.camada] !== undefined) ? projetoAtual.volumes_camadas[cenaRaw.camada] : 1.0;
        img.volume = Math.min(baseVol * multV, 1.0);
        
        if (isPlaying) {
            if (img.paused) {
                img.currentTime = tempoAlvo;
                img.play().catch(e => {}); 
            } else if (Math.abs(img.currentTime - tempoAlvo) > 0.25) {
                img.currentTime = tempoAlvo;
            }
        } else {
            if (!img.paused) img.pause();
            if (Math.abs(img.currentTime - tempoAlvo) > 0.05) {
                img.currentTime = tempoAlvo;
            }
        }
    }
    
    let progressoCru = duracao_cena > 0 ? Math.min(t_local / duracao_cena, 1.0) : 1.0;
    
    let animStart = cenaRaw.anim_start !== undefined ? cenaRaw.anim_start : 0.0;
    let animEnd = cenaRaw.anim_end !== undefined ? cenaRaw.anim_end : 1.0;
    let easing = cenaRaw.anim_easing || 'linear';
    
    let progresso = calculateEasedProgress(progressoCru, animStart, animEnd, easing);
    
    let fx = 0.5, fy = 0.5; if (cenaRaw.quadros_foco && cenaRaw.quadros_foco.length > 0) { let cxTotal = 0, cyTotal = 0; cenaRaw.quadros_foco.forEach(q => { let row = Math.floor((q - 1) / 3); let col = (q - 1) % 3; cxTotal += (col * (1/3)) + (1/6); cyTotal += (row * (1/3)) + (1/6); }); fx = cxTotal / cenaRaw.quadros_foco.length; fy = cyTotal / cenaRaw.quadros_foco.length; }
    
    let midiaW = isVideo ? img.videoWidth : img.width;
    let midiaH = isVideo ? img.videoHeight : img.height;
    
    let scaleX = canvasRef.width / midiaW; let scaleY = canvasRef.height / midiaH; let baseScale = Math.max(scaleX, scaleY);
    let drawW = midiaW * baseScale; let drawH = midiaH * baseScale;
    let imgCenterX = drawW * fx; let imgCenterY = drawH * fy;
    let targetX = (canvasRef.width / 2) - imgCenterX; let targetY = (canvasRef.height / 2) - imgCenterY;
    let finalX = Math.max(canvasRef.width - drawW, Math.min(0, targetX)); let finalY = Math.max(canvasRef.height - drawH, Math.min(0, targetY));

    let modo = getAnimacao(cenaRaw, cenaRaw.id); 
    let zoomPadrao = cenaRaw.zoom_intensity !== undefined ? cenaRaw.zoom_intensity : 0.15;
    let currentScale = 1.0; let panOffsetX = 0, panOffsetY = 0;
    
    if (modo === 'zoom_in') { 
        currentScale = 1.0 + (zoomPadrao * progresso); 
    } else if (modo === 'zoom_out') { 
        currentScale = (1.0 + zoomPadrao) - (zoomPadrao * progresso); 
    } else if (modo === 'pan') { 
        currentScale = 1.15; 
        let offsetMax = canvasRef.width * 0.05; 
        panOffsetX = -offsetMax + (offsetMax * 2) * progresso; 
    }

    ctxAlvo.save(); ctxAlvo.clearRect(0, 0, canvasRef.width, canvasRef.height); ctxAlvo.translate(canvasRef.width / 2, canvasRef.height / 2); ctxAlvo.scale(currentScale, currentScale); ctxAlvo.translate(-canvasRef.width / 2, -canvasRef.height / 2); ctxAlvo.translate(panOffsetX, panOffsetY); ctxAlvo.drawImage(img, finalX, finalY, drawW, drawH); ctxAlvo.restore();
}

function renderCanvas(tempoSegundos) {
    if(isPreviewing) return; 
    
    const canvas = document.getElementById('previewCanvas');
    let idxPlano = null; 
    for (let i = 0; i < timelinePlanificada.length; i++) { 
        let b = timelinePlanificada[i]; 
        if (tempoSegundos >= b.inicio && tempoSegundos < b.fim) { idxPlano = i; break; } 
    }
    
    let isMusicaClicada = typeof itemClicadoMenu === 'string' && itemClicadoMenu.startsWith('musica_');
    
    if (itemClicadoMenu !== 'audio_locucao' && !isMusicaClicada) {
        let currentCenaId = (idxPlano !== null && !timelinePlanificada[idxPlano].is_black) ? timelinePlanificada[idxPlano].id : null;
        if (cenaAtivaPropriedades !== currentCenaId) {
            cenaAtivaPropriedades = currentCenaId;
            if (currentCenaId !== null) atualizarPainel(currentCenaId);
            else document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`;
        }
    }

    if (idxPlano === null || timelinePlanificada[idxPlano].is_black) { 
        const ctxA = offCanvasA.getContext('2d');
        ctxA.fillStyle = '#000000'; ctxA.fillRect(0, 0, offCanvasA.width, offCanvasA.height);
        WebGLRenderer.render('none', offCanvasA, null, 0); 
        return; 
    }

    let flatA = timelinePlanificada[idxPlano]; let rawA = projetoAtual.cenas[flatA.id];
    let durTransAnterior = 0;
    if (idxPlano > 0) { let flatPrev = timelinePlanificada[idxPlano - 1]; if (!flatPrev.is_black) { let rawPrev = projetoAtual.cenas[flatPrev.id]; let tipoTPrev = getTransicao(rawPrev, rawPrev.id); if (tipoTPrev !== 'nenhuma') durTransAnterior = Math.min(1.0, (flatPrev.fim - flatPrev.inicio)*0.5, (flatA.fim - flatA.inicio)*0.5); } }
    
    let t_local_A = (tempoSegundos - flatA.inicio) + durTransAnterior; let duracaoVisualA = (flatA.fim - flatA.inicio) + durTransAnterior;
    let inTransition = false; let flatB = null; let rawB = null; let progressoTrans = 0; let tipoTrans = getTransicao(rawA, rawA.id); let duracaoTrans = 0;

    if (idxPlano < timelinePlanificada.length - 1 && tipoTrans !== 'nenhuma') {
        flatB = timelinePlanificada[idxPlano + 1];
        if (!flatB.is_black) {
            rawB = projetoAtual.cenas[flatB.id]; let duracaoB = flatB.fim - flatB.inicio;
            duracaoTrans = Math.min(1.0, (flatA.fim - flatA.inicio) * 0.5, duracaoB * 0.5); 
            let inicioTrans = flatA.fim - duracaoTrans;
            if (tempoSegundos >= inicioTrans && tempoSegundos <= flatA.fim) { inTransition = true; progressoTrans = (tempoSegundos - inicioTrans) / duracaoTrans; }
        } else { tipoTrans = 'nenhuma'; }
    }

    Object.keys(imageCache).forEach(key => {
        let img = imageCache[key];
        if (img instanceof HTMLVideoElement && !img.paused) {
            if (rawA && key == rawA.id) return; 
            if (rawB && key == rawB.id) return; 
            img.pause();
        }
    });

    const ctxA = offCanvasA.getContext('2d'); renderizarCenaBase(ctxA, canvas, rawA, imageCache[rawA.id], t_local_A, duracaoVisualA);
    if (!inTransition) { WebGLRenderer.render('none', offCanvasA, null, 0); return; }

    const ctxB = offCanvasB.getContext('2d'); let t_local_B = tempoSegundos - (flatA.fim - duracaoTrans); renderizarCenaBase(ctxB, canvas, rawB, imageCache[rawB.id], t_local_B, (flatB.fim - flatB.inicio) + duracaoTrans);
    WebGLRenderer.render(tipoTrans, offCanvasA, offCanvasB, progressoTrans);
}

function togglePlay() { 
    const btn = document.getElementById('btnPlayPause'); 
    if (isPlaying) { 
        AudioEngine.pausar(); 
        isPlaying = false; 
        btn.innerHTML = '<i class="ph-fill ph-play"></i>'; 
        btn.classList.remove('play'); 
        
        Object.values(imageCache).forEach(img => { 
            if (img instanceof HTMLVideoElement && !img.paused) img.pause(); 
        });
    } else { 
        AudioEngine.tocar(); 
        isPlaying = true; 
        btn.innerHTML = '<i class="ph-fill ph-pause"></i>'; 
        btn.classList.add('play'); 
        loopDeReproducao(); 
    } 
}

function buscarTempo(segundos) { if (segundos < 0) segundos = 0; if (segundos > projetoAtual.duracao) segundos = projetoAtual.duracao; AudioEngine.buscar(segundos); timeline.setCustomTime(segToDate(segundos), 'agulha'); atualizarMostradorTempo(segundos); renderCanvas(segundos); }
function stepFrame(direcao) { let passo = direcao * (1 / FPS); let tempoAtual = AudioEngine.obterTempoAtual(); if (isPlaying) togglePlay(); buscarTempo(tempoAtual + passo); }
function loopDeReproducao() { if (!isPlaying) return; let currentTime = AudioEngine.obterTempoAtual(); timeline.setCustomTime(segToDate(currentTime), 'agulha'); atualizarMostradorTempo(currentTime); renderCanvas(currentTime); if (currentTime >= projetoAtual.duracao - 0.1) { togglePlay(); buscarTempo(0); } else { requestAnimationFrame(loopDeReproducao); } }
function atualizarMostradorTempo(segundos) { document.getElementById('timeDisplay').innerText = `${formatTime(segundos)} / ${formatTime(projetoAtual.duracao)}`; }

async function uploadMidia(event) { 
    const file = event.target.files[0]; if (!file) return; 
    const formData = new FormData(); formData.append("file", file); 

    // INJEÇÃO: Feedback visual imediato na biblioteca
    const listaMidias = document.querySelector('.lista-midias');
    if (listaMidias) {
        listaMidias.insertAdjacentHTML('afterbegin', `
            <div class="item-midia" id="loading_upload_lib" style="display:flex; flex-direction:column; align-items:center; justify-content:center; background: rgba(0,0,0,0.7);">
                <div class="spinner-carregando" style="width:24px; height:24px; border-width:2px; border-top-color:var(--primary-cyan);"></div>
                <span style="font-size:10px; margin-top:8px; color:var(--primary-cyan);">Enviando...</span>
            </div>
        `);
    }

    await fetch('/api/upload_midia', { method: 'POST', body: formData }); 
    carregarBiblioteca(); // Ao recarregar a lista, o card temporário será sobrescrito pela mídia real
}

function acionarSubstituicao() { if (itemClicadoMenu === null) return; document.getElementById('menuContexto').style.display = 'none'; document.getElementById('fileReplace').click(); }

async function uploadSubstituicao(event) {
    const file = event.target.files[0]; if (!file || itemClicadoMenu === null) return;
    const formData = new FormData(); formData.append("file", file); formData.append("id_cena", itemClicadoMenu);
    
    const res = await fetch('/api/substituir_imagem', { method: 'POST', body: formData });
    const data = await res.json();
    
    if(data.status === 'ok') {
        projetoAtual.cenas[itemClicadoMenu].arquivo_origem = data.novo_arquivo;
        delete imageCache[itemClicadoMenu];
        sincronizarJSON(); 
        reconstruirDaMemoria(); 
        verificarECriarCamadas();
        pushHistory(); 
        carregarBiblioteca();
    }
}

window.inserirMidiaNaTimeline = function(nomeArquivo, idRef = null, camadaAlvo = null) { 
    const tempoAgulha = dateToSeg(timeline.getCustomTime('agulha')); 
    const novoId = projetoAtual.cenas.length; 
    
    let isVideo = nomeArquivo && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(nomeArquivo);

    let camadaFinal = 'v1';
    if (camadaAlvo) {
        camadaFinal = camadaAlvo;
    } else {
        let num = 1;
        while(true) {
            let colisoes = itemsDataset.get({ filter: function(outro) {
                return outro.group === 'v' + num && tempoAgulha < dateToSeg(outro.end) && (tempoAgulha + 3.0) > dateToSeg(outro.start);
            }});
            if (colisoes.length === 0) {
                camadaFinal = 'v' + num;
                break;
            }
            num++;
        }
    }

    // Por padrão, entra com 3 segundos
    const novaCena = { id: novoId, inicio: tempoAgulha, fim: tempoAgulha + 3.0, camada: camadaFinal, quadros_foco: [5], arquivo_origem: nomeArquivo, animacao: 'auto', transicao: 'auto', foco_manual: false }; 
    projetoAtual.cenas.push(novaCena); 
    
    verificarECriarCamadas(); 
    itemsDataset.add({ id: novoId, group: camadaFinal, content: criarConteudoCena(novoId, nomeArquivo), start: segToDate(novaCena.inicio), end: segToDate(novaCena.fim) }); 
    
    carregarImagensNaMemoria(); sincronizarJSON(); pushHistory(); renderCanvas(AudioEngine.obterTempoAtual()); 
    
    // >>> NOVO: Puxa a duração exata do vídeo no momento em que ele entra <<<
    if (isVideo) {
        let tempVid = document.createElement('video');
        tempVid.src = `/proxy/preview/midia/${encodeURIComponent(nomeArquivo)}`;
        tempVid.onloadedmetadata = function() {
            let durReal = tempVid.duration;
            if (durReal && durReal > 0) {
                projetoAtual.cenas[novoId].fim = tempoAgulha + durReal;
                projetoAtual.cenas[novoId].duracao_maxima = durReal; // Grava a trava definitiva!
                itemsDataset.update({ id: novoId, end: segToDate(tempoAgulha + durReal) });
                sincronizarJSON();
                renderCanvas(AudioEngine.obterTempoAtual());
            }
        };
    }
};

window.removerTodasCenas = function() {
    if(confirm("Tem certeza que deseja apagar TODAS as cenas de vídeo e imagens da timeline?")) {
        projetoAtual.cenas.forEach((c, idx) => {
            if(c) itemsDataset.remove(idx);
        });
        projetoAtual.cenas = [];
        sincronizarJSON();
        pushHistory();
        itemClicadoMenu = null;
        cenaAtivaPropriedades = -1;
        document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`;
        renderCanvas(AudioEngine.obterTempoAtual());
    }
};

if (!document.getElementById('fileUploadTimeline')) {
    let input = document.createElement('input');
    input.type = 'file';
    input.id = 'fileUploadTimeline';
    input.style.display = 'none';
    input.accept = 'image/*,video/*,audio/*';
    
    input.onchange = async function(event) {
    const file = event.target.files[0]; if (!file) return; 
    const formData = new FormData(); formData.append("file", file); 
    
    document.getElementById('painelProps').innerHTML = `<div class="info-box" style="text-align:center;"><p style="color:var(--primary-cyan);"><i class="ph ph-spinner-gap"></i> Sincronizando arquivo com o servidor...</p></div>`;
    
    // INJEÇÃO: Criar bloco fantasma na Timeline instantaneamente
    const tempoAgulha = dateToSeg(timeline.getCustomTime('agulha'));
    let camada = window.camadaAlvoNovaCena || 'v1';
    let idTemp = 'upload_' + Date.now();
    itemsDataset.add({
        id: idTemp, group: camada, start: segToDate(tempoAgulha), end: segToDate(tempoAgulha + 3.0),
        content: `<div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.6); border-radius:4px;"><div class="spinner-carregando" style="width:20px;height:20px;border-width:2px;border-top-color:var(--primary-cyan);"></div><span style="font-size:11px; margin-left:8px; color:white;">Processando Proxy...</span></div>`
    });

    try {
        let resBibAntiga = await fetch('/api/biblioteca');
        let bibAntiga = await resBibAntiga.json();
        let arquivosAntigos = bibAntiga.importadas || [];

        let resUpload = await fetch('/api/upload_midia', { method: 'POST', body: formData }); 
        let dadosUpload = {};
        try { dadosUpload = await resUpload.json(); } catch(e){}

        let nomeRealSalvo = null;
        if (dadosUpload && dadosUpload.nome_arquivo) nomeRealSalvo = dadosUpload.nome_arquivo;
        else if (dadosUpload && dadosUpload.arquivo) nomeRealSalvo = dadosUpload.arquivo;

        let tentativas = 0;
        while (!nomeRealSalvo && tentativas < 4) {
            await new Promise(r => setTimeout(r, 500)); 
            let resBibNova = await fetch('/api/biblioteca');
            let bibNova = await resBibNova.json();
            let arquivosNovos = bibNova.importadas || [];
            
            nomeRealSalvo = arquivosNovos.find(f => !arquivosAntigos.includes(f));
            tentativas++;
        }

        if (!nomeRealSalvo) nomeRealSalvo = file.name.replace(/ /g, '_'); 

        carregarBiblioteca(); 
        
        // INJEÇÃO: Remove o bloco fantasma e insere o arquivo já codificado
        itemsDataset.remove(idTemp);
        inserirMidiaNaTimeline(nomeRealSalvo, null, camada);
        
        setTimeout(() => { buscarTempo(dateToSeg(timeline.getCustomTime('agulha'))); }, 150);

    } catch(e) {
        console.error(e);
        itemsDataset.remove(idTemp); // Limpa a sujeira se a rede cair
        alert("Erro ao fazer upload da imagem.");
    }
    event.target.value = ''; 
};
    document.body.appendChild(input);
}

function alternarQuadranteMini(num, idx) {
    let cena = projetoAtual.cenas[idx];
    let index = cena.quadros_foco.indexOf(num);
    if (index > -1) { cena.quadros_foco.splice(index, 1); } 
    else {
        if (cena.quadros_foco.length >= 3) { alert("Máximo de 3 pontos focais."); return; }
        cena.quadros_foco.push(num);
    }
    if (cena.quadros_foco.length === 0) cena.quadros_foco = [5];
    cena.quadros_foco.sort((a,b) => a-b);
    cena.foco_manual = true; 
    atualizarPainel(idx);
    pushHistory();
    renderCanvas(AudioEngine.obterTempoAtual());
}

async function acionarIAFocal() { if (itemClicadoMenu === null) return; const idCena = itemClicadoMenu; const nomeOriginal = itemsDataset.get(idCena).content; const conteudoCarregando = `<div class="spinner-carregando"></div><span style="display:inline-block; vertical-align:middle; font-size:10px;">Analisando...</span>`; itemsDataset.update({ id: idCena, className: 'item-carregando-ia', content: conteudoCarregando }); try { const resposta = await fetch('/api/detectar_foco_ia', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cena_id: idCena }) }); const dados = await resposta.json(); if(dados.status === "ok") { projetoAtual.cenas[idCena].quadros_foco = dados.novo_foco; projetoAtual.cenas[idCena].foco_manual = false; atualizarPainel(idCena); pushHistory(); renderCanvas(AudioEngine.obterTempoAtual()); } } catch (e) {} finally { itemsDataset.update({ id: idCena, className: '', content: nomeOriginal }); } }
function abrirModalFoco() { if (itemClicadoMenu === null) return; document.getElementById('menuContexto').style.display = 'none'; const idCena = itemClicadoMenu; const cena = projetoAtual.cenas[idCena]; quadrantesSelecionados = [...cena.quadros_foco]; document.getElementById('imgFocoManual').src = cena.arquivo_origem ? `/proxy/preview/midia/${encodeURIComponent(cena.arquivo_origem)}` : `/proxy/preview/cena/${idCena}`; const overlay = document.getElementById('gridOverlay'); overlay.innerHTML = ''; for(let i = 1; i <= 9; i++) { const cell = document.createElement('div'); cell.className = 'grid-cell'; if (quadrantesSelecionados.includes(i)) cell.classList.add('selecionado'); cell.innerText = i; cell.onclick = () => alternarQuadrante(i, cell); overlay.appendChild(cell); } document.getElementById('modalFoco').style.display = 'flex'; }
function alternarQuadrante(num, element) { const index = quadrantesSelecionados.indexOf(num); if (index > -1) { quadrantesSelecionados.splice(index, 1); element.classList.remove('selecionado'); } else { if (quadrantesSelecionados.length >= 3) { alert("Máx 3"); return; } quadrantesSelecionados.push(num); element.classList.add('selecionado'); } }
function fecharModalFoco() { document.getElementById('modalFoco').style.display = 'none'; }
function salvarFocoManual() { if (quadrantesSelecionados.length === 0) quadrantesSelecionados = [5]; projetoAtual.cenas[itemClicadoMenu].quadros_foco = quadrantesSelecionados.sort((a,b) => a-b); projetoAtual.cenas[itemClicadoMenu].foco_manual = true; atualizarPainel(itemClicadoMenu); fecharModalFoco(); pushHistory(); renderCanvas(AudioEngine.obterTempoAtual()); }

function removerCenaSelecionada(bypassConfirm = false) { 
    let idAlvo = itemClicadoMenu;
    if(idAlvo === null) idAlvo = cenaAtivaPropriedades; 
    if(idAlvo === null || idAlvo === -1) return;

    if(bypassConfirm || confirm("Remover esta cena da timeline? O vídeo ficará preto neste trecho.")) { 
        itemsDataset.remove(idAlvo); projetoAtual.cenas[idAlvo] = null; document.getElementById('menuContexto').style.display = 'none'; 
        sincronizarJSON(); pushHistory(); renderCanvas(AudioEngine.obterTempoAtual()); itemClicadoMenu = null;
verificarECriarCamadas();
    } 
}

function sincronizarJSON() { 
    let maxDuracao = 0;

    let locItem = itemsDataset.get('audio_locucao');
    if (locItem) maxDuracao = dateToSeg(locItem.end);

    projetoAtual.cenas.forEach((cena, idx) => { 
        if(!cena) return; 
        cena.id = idx; 
        let dsItem = itemsDataset.get(idx); 
        if (dsItem) { 
            cena.inicio = dateToSeg(dsItem.start); 
            cena.fim = dateToSeg(dsItem.end); 
            cena.camada = dsItem.group; 
            if (cena.fim > maxDuracao) maxDuracao = cena.fim;
        } 
    }); 
    
    if (projetoAtual.faixas_musicais) {
        projetoAtual.faixas_musicais.forEach((faixa, idx) => {
            if(!faixa) return;
            let dsItem = itemsDataset.get(`musica_${idx}`);
            if (dsItem) {
                faixa.inicio = dateToSeg(dsItem.start);
                faixa.fim = dateToSeg(dsItem.end);
            }
            if (faixa.fim > maxDuracao) maxDuracao = faixa.fim;
        });
    }

    if (maxDuracao > 0) projetoAtual.duracao = maxDuracao;

    timelinePlanificada = achatarCamadasJS(); 
    
    let tempoAtual = typeof AudioEngine !== 'undefined' ? AudioEngine.obterTempoAtual() : 0;
    if(typeof atualizarMostradorTempo === 'function') atualizarMostradorTempo(tempoAtual);
}

function toggleCustomSelect(elementId) {
    document.querySelectorAll('.select-items').forEach(el => { if(el.id !== elementId) el.classList.remove('select-show'); });
    document.getElementById(elementId).classList.toggle('select-show');
}

function changeCustomSelect(idx, atributo, valor, label, iconeHtml, menuId, headerId) {
    document.getElementById(headerId).innerHTML = `${iconeHtml} ${label}`;
    document.getElementById(menuId).classList.remove('select-show');
    atualizarAtributoCena(idx, atributo, valor);
    pararPreviewEfeito(); 
}

function iniciarPreviewEfeito(tipo, valor, idxCena) {
    if(isPlaying) togglePlay(); 
    if(isPreviewing) pararPreviewEfeito(); 
    
    isPreviewing = true;
    previewStartTime = performance.now();
    
    if(tipo === 'transicao' && valor !== 'nenhuma' && valor !== 'auto') {
        let audioKey = Object.keys(AudioEngine.mapaSFX).find(k => valor.includes(k.replace('_direita','').replace('_esquerda','').replace('_cima','').replace('_baixo','')));
        if (!audioKey) audioKey = valor;
        if (AudioEngine.sfxBuffers[audioKey]) {
            previewSfxNode = AudioEngine.ctx.createBufferSource(); 
            previewSfxNode.buffer = AudioEngine.sfxBuffers[audioKey];
            window.previewSfxGainNode = AudioEngine.ctx.createGain(); 
            let transVol = projetoAtual.cenas[idxCena].transition_volume !== undefined ? projetoAtual.cenas[idxCena].transition_volume : 1.0;
            window.previewSfxLayer = projetoAtual.cenas[idxCena].camada || 'v1';
            let multV = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas[window.previewSfxLayer] !== undefined) ? projetoAtual.volumes_camadas[window.previewSfxLayer] : 1.0;
            
            window.previewSfxBaseVol = 0.20 * transVol;
            window.previewSfxGainNode.gain.value = window.previewSfxBaseVol * multV; 
            
            previewSfxNode.connect(window.previewSfxGainNode); window.previewSfxGainNode.connect(AudioEngine.ctx.destination);
            previewSfxNode.start();
        }
    }

    function loopPreview(time) {
        if(!isPreviewing) return;
        
        let elapsed = (time - previewStartTime) / 1000;
        let duration = tipo === 'animacao' ? 2.0 : 1.0; 
        
        if(elapsed > duration) {
            previewStartTime = time;
            elapsed = 0;
            if(tipo === 'transicao' && previewSfxNode) {
                try{ previewSfxNode.stop(); }catch(e){}
                let audioKey = Object.keys(AudioEngine.mapaSFX).find(k => valor.includes(k.replace('_direita','').replace('_esquerda','').replace('_cima','').replace('_baixo','')));
                if (!audioKey) audioKey = valor;
                if (AudioEngine.sfxBuffers[audioKey]) {
                    previewSfxNode = AudioEngine.ctx.createBufferSource(); 
                    previewSfxNode.buffer = AudioEngine.sfxBuffers[audioKey];
                    let gainNode = AudioEngine.ctx.createGain(); 
                    
                    let transVol = projetoAtual.cenas[idxCena].transition_volume !== undefined ? projetoAtual.cenas[idxCena].transition_volume : 1.0;
                    gainNode.gain.value = 0.20 * transVol; 
                    
                    previewSfxNode.connect(gainNode); gainNode.connect(AudioEngine.ctx.destination);
                    previewSfxNode.start();
                }
            }
        }
        
        let progressCru = elapsed / duration;
        
        const canvas = document.getElementById('previewCanvas');
        const ctxA = offCanvasA.getContext('2d'); const ctxB = offCanvasB.getContext('2d');
        let rawA = projetoAtual.cenas[idxCena];
        
        if(tipo === 'animacao') {
            let animOriginal = rawA.animacao; rawA.animacao = valor;
            let animStartOriginal = rawA.anim_start; let animEndOriginal = rawA.anim_end; let animEasingOriginal = rawA.anim_easing;
            rawA.anim_start = 0.0; rawA.anim_end = 1.0; rawA.anim_easing = 'linear';

            renderizarCenaBase(ctxA, canvas, rawA, imageCache[rawA.id], progressCru * 2.0, 2.0);
            
            rawA.animacao = animOriginal; rawA.anim_start = animStartOriginal; rawA.anim_end = animEndOriginal; rawA.anim_easing = animEasingOriginal;
            WebGLRenderer.render('none', offCanvasA, null, 0); 
        } else {
            let idxBFlat = timelinePlanificada.findIndex(b => b.id === idxCena) + 1;
            let rawB = null;
            if(idxBFlat > 0 && idxBFlat < timelinePlanificada.length && !timelinePlanificada[idxBFlat].is_black) {
                rawB = projetoAtual.cenas[timelinePlanificada[idxBFlat].id];
            }
            renderizarCenaBase(ctxA, canvas, rawA, imageCache[rawA.id], 1.0, 2.0); 
            if(rawB && imageCache[rawB.id]) {
                renderizarCenaBase(ctxB, canvas, rawB, imageCache[rawB.id], progressCru, 2.0);
                WebGLRenderer.render(valor, offCanvasA, offCanvasB, progressCru);
            } else {
                ctxB.fillStyle = '#000000'; ctxB.fillRect(0, 0, canvas.width, canvas.height);
                WebGLRenderer.render(valor, offCanvasA, offCanvasB, progressCru);
            }
        }
        previewRaf = requestAnimationFrame(loopPreview);
    }
    previewRaf = requestAnimationFrame(loopPreview);
}

function pararPreviewEfeito() {
    if(!isPreviewing) return;
    isPreviewing = false;
    if(previewRaf) cancelAnimationFrame(previewRaf);
    if(previewSfxNode) { try{ previewSfxNode.stop(); }catch(e){} previewSfxNode = null; }
    renderCanvas(AudioEngine.obterTempoAtual()); 
}

let dragNumState = null;

window.startDragZoom = function(e, idx) {
    e.preventDefault();
    let valAtual = projetoAtual.cenas[idx].zoom_intensity !== undefined ? projetoAtual.cenas[idx].zoom_intensity : 0.15;
    dragNumState = { idx: idx, startY: e.clientY, startVal: valAtual };
    document.body.style.cursor = 'ns-resize';
    document.addEventListener('mousemove', onDragZoom);
    document.addEventListener('mouseup', stopDragZoom);
};

function onDragZoom(e) {
    if(!dragNumState) return;
    let delta = dragNumState.startY - e.clientY;
    let val = dragNumState.startVal + (delta * 0.005); 
    if(val < 0.01) val = 0.01;
    
    projetoAtual.cenas[dragNumState.idx].zoom_intensity = val;
    
    let label = document.getElementById('zoomLabel');
    let slider = document.getElementById('zoomSlider');
    if(label) label.innerText = (val * 100).toFixed(0) + '%';
    if(slider) slider.value = Math.min(val, 1.0);
    
    let isGlobal = document.getElementById('zoomGlobalCheck') && document.getElementById('zoomGlobalCheck').checked;
    if (isGlobal) { projetoAtual.cenas.forEach(c => { if(c) c.zoom_intensity = val; }); }
    
    renderCanvas(AudioEngine.obterTempoAtual());
}

function stopDragZoom() {
    if(dragNumState) {
        dragNumState = null;
        document.body.style.cursor = 'default';
        document.removeEventListener('mousemove', onDragZoom);
        document.removeEventListener('mouseup', stopDragZoom);
        pushHistory(); sincronizarJSON();
    }
}

window.onZoomSliderChange = function(idx, valStr) {
    let val = parseFloat(valStr);
    projetoAtual.cenas[idx].zoom_intensity = val;
    let label = document.getElementById('zoomLabel');
    if(label) label.innerText = (val * 100).toFixed(0) + '%';
    
    let isGlobal = document.getElementById('zoomGlobalCheck') && document.getElementById('zoomGlobalCheck').checked;
    if (isGlobal) { projetoAtual.cenas.forEach(c => { if(c) c.zoom_intensity = val; }); }
    
    renderCanvas(AudioEngine.obterTempoAtual());
    pushHistory(); sincronizarJSON();
};

window.updateAnimTiming = function(idx) {
    let s = parseInt(document.getElementById('animStart').value) / 100.0;
    let e = parseInt(document.getElementById('animEnd').value) / 100.0;
    if (s > e - 0.05) { 
        if(event.target.id === 'animStart') { s = e - 0.05; document.getElementById('animStart').value = s*100; }
        else { e = s + 0.05; document.getElementById('animEnd').value = e*100; }
    }
    
    let isGlobal = document.getElementById('animGlobalCheck') && document.getElementById('animGlobalCheck').checked;
    projetoAtual.cenas[idx].anim_start = s; projetoAtual.cenas[idx].anim_end = e;
    
    if (isGlobal) { projetoAtual.cenas.forEach(c => { if(c) { c.anim_start = s; c.anim_end = e; } }); }
    
    renderCanvas(AudioEngine.obterTempoAtual());
    sincronizarJSON();
};

window.updateAnimEasing = function(idx, val) {
    let isGlobal = document.getElementById('animGlobalCheck') && document.getElementById('animGlobalCheck').checked;
    projetoAtual.cenas[idx].anim_easing = val;
    if (isGlobal) { projetoAtual.cenas.forEach(c => { if(c) c.anim_easing = val; }); }
    pushHistory(); sincronizarJSON(); renderCanvas(AudioEngine.obterTempoAtual());
};

window.updateTransVol = function(idx, valStr) {
    let val = parseFloat(valStr);
    let label = document.getElementById('transVolLabel');
    if(label) label.innerText = (val * 100).toFixed(0) + '%';
    
    let isLocal = document.getElementById('transLocalCheck') && document.getElementById('transLocalCheck').checked;
// >>> ATUALIZA O PREVIEW EM TEMPO REAL AO ARRASTAR <<<
    if (window.previewSfxGainNode) {
        window.previewSfxBaseVol = 0.20 * val;
        let multV = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas[window.previewSfxLayer] !== undefined) ? projetoAtual.volumes_camadas[window.previewSfxLayer] : 1.0;
        window.previewSfxGainNode.gain.value = window.previewSfxBaseVol * multV;
    }
    
    projetoAtual.cenas[idx].transition_volume = val;
    projetoAtual.cenas[idx].trans_vol_local = isLocal;
    
    if (!isLocal) {
        let sound = getTransicao(projetoAtual.cenas[idx], idx);
        projetoAtual.cenas.forEach((c, i) => {
            if (c && getTransicao(c, i) === sound) {
                c.transition_volume = val;
                c.trans_vol_local = false;
            }
        });
    }
    sincronizarJSON();
};

window.updateTransVolLocal = function(idx, isLocal) {
    let val = parseFloat(document.getElementById('transVolSlider').value);
// >>> ATUALIZA O PREVIEW EM TEMPO REAL AO ARRASTAR <<<
    if (window.previewSfxGainNode) {
        window.previewSfxBaseVol = 0.20 * val;
        let multV = (projetoAtual.volumes_camadas && projetoAtual.volumes_camadas[window.previewSfxLayer] !== undefined) ? projetoAtual.volumes_camadas[window.previewSfxLayer] : 1.0;
        window.previewSfxGainNode.gain.value = window.previewSfxBaseVol * multV;
    }
    projetoAtual.cenas[idx].transition_volume = val;
    projetoAtual.cenas[idx].trans_vol_local = isLocal;
    
    if (!isLocal) {
        let sound = getTransicao(projetoAtual.cenas[idx], idx);
        projetoAtual.cenas.forEach((c, i) => {
            if (c && getTransicao(c, i) === sound) {
                c.transition_volume = val;
                c.trans_vol_local = false;
            }
        });
    }
    pushHistory(); sincronizarJSON();
};

window.toggleAdvancedMenu = function() {
    window._advMenuOpen = !window._advMenuOpen;
    document.getElementById('advContent').style.display = window._advMenuOpen ? 'block' : 'none';
    document.getElementById('advIcon').className = window._advMenuOpen ? 'ph-fill ph-caret-down' : 'ph-fill ph-caret-right';
};

window.updateVideoVol = function(idx, valStr) {
    let val = parseFloat(valStr);
    projetoAtual.cenas[idx].volume_video = val;
    
    let label = document.getElementById('videoVolLabel');
    if(label) label.innerText = (val * 100).toFixed(0) + '%';
    
    if (imageCache[idx] && imageCache[idx] instanceof HTMLVideoElement) {
        imageCache[idx].volume = val;
    }
    sincronizarJSON();
};

function atualizarPainel(idx) { 
    const cena = projetoAtual.cenas[idx]; if(!cena) return; const duracao = (cena.fim - cena.inicio).toFixed(2); 
    
    let html = `<div class="prop-header"><span>Cena ${idx + 1} &bull; Camada ${cena.camada || 'v1'}</span><span>${duracao}s</span></div>`; 
    
    let imgSrc = cena.arquivo_origem ? `/proxy/thumb/midia/${encodeURIComponent(cena.arquivo_origem)}?t=${Date.now()}` : `/proxy/thumb/cena/${idx}?t=${Date.now()}`;
    let isManual = cena.foco_manual ? "" : " (IA)";
    
    let miniGridHTML = `
    <div style="text-align: center; margin: 10px 0;">
        <div style="position: relative; display: inline-block; border: 1px solid var(--border-color); border-radius: 6px; overflow: hidden; background: #000; box-shadow: 0 4px 8px rgba(0,0,0,0.5); max-width: 100%;">
            <img src="${imgSrc}" style="max-width: 100%; max-height: 160px; display: block;" onerror="this.style.display='none'">
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr);">`;

    for(let i=1; i<=9; i++) {
        let isSel = cena.quadros_foco.includes(i);
        let bg = isSel ? 'rgba(0, 210, 255, 0.4)' : 'transparent';
        let border = isSel ? '1px solid var(--primary-cyan)' : '1px solid rgba(255,255,255,0.1)';
        let color = isSel ? '#fff' : 'rgba(255,255,255,0.3)';
        let textShadow = isSel ? '0 2px 4px rgba(0,0,0,0.8)' : 'none';
        miniGridHTML += `<div style="display: flex; align-items: center; justify-content: center; font-size: 14px; background: ${bg}; border: ${border}; color: ${color}; text-shadow: ${textShadow}; box-sizing: border-box; cursor: pointer; transition: 0.1s;" onclick="alternarQuadranteMini(${i}, ${idx})" onmouseover="this.style.backgroundColor='rgba(0, 210, 255, 0.2)'" onmouseout="this.style.backgroundColor='${bg}'">${i}</div>`;
    }
    miniGridHTML += `</div></div></div>`;

    html += `<div class="info-box" style="text-align: center; background: transparent; border:none; padding: 0;">
        <label style="justify-content: center;"><i class="ph ph-crosshair"></i> Ponto Focal${isManual}:</label>
        ${miniGridHTML}
        <button class="btn-outline" style="margin-top:5px; font-size:0.8em; padding: 6px;" onclick="itemClicadoMenu=${idx}; abrirModalFoco()">Abrir grade maior</button>
    </div>`;

    let animAtual = cena.animacao || "auto"; 
    let objAnim = OPCOES_ANIMACAO.find(o => o.id === animAtual) || OPCOES_ANIMACAO[0];
    let animIcon = `<i class="ph ${objAnim.icone}"></i>`;
    let htmlAnimItems = OPCOES_ANIMACAO.map(o => `<div class="select-item" onmouseenter="iniciarPreviewEfeito('animacao', '${o.id}', ${idx})" onmouseleave="pararPreviewEfeito()" onclick="changeCustomSelect(${idx}, 'animacao', '${o.id}', '${o.label}', '<i class=\\'ph ${o.icone}\\'></i>', 'menuAnim', 'headAnim')"><i class="ph ${o.icone}"></i> ${o.label}</div>`).join('');
    
    html += `
    <div class="info-box">
        <label><i class="ph ph-arrows-out-cardinal"></i> Movimento:</label>
        <div class="custom-select">
            <div class="select-selected" id="headAnim" onclick="toggleCustomSelect('menuAnim')">${animIcon} ${objAnim.label}</div>
            <div class="select-items" id="menuAnim">${htmlAnimItems}</div>
        </div>
    </div>`; 
    
    let transAtual = cena.transicao || "auto"; 
    let objTrans = OPCOES_TRANSICAO.find(o => o.id === transAtual) || OPCOES_TRANSICAO[0];
    let transIcon = `<i class="ph ${objTrans.icone}"></i>`;
    let htmlTransItems = OPCOES_TRANSICAO.map(o => `<div class="select-item" onmouseenter="iniciarPreviewEfeito('transicao', '${o.id}', ${idx})" onmouseleave="pararPreviewEfeito()" onclick="changeCustomSelect(${idx}, 'transicao', '${o.id}', '${o.label}', '<i class=\\'ph ${o.icone}\\'></i>', 'menuTrans', 'headTrans')"><i class="ph ${o.icone}"></i> ${o.label}</div>`).join('');

    html += `
    <div class="info-box">
        <label><i class="ph ph-magic-wand"></i> Transição:</label>
        <div class="custom-select">
            <div class="select-selected" id="headTrans" onclick="toggleCustomSelect('menuTrans')">${transIcon} ${objTrans.label}</div>
            <div class="select-items" id="menuTrans">${htmlTransItems}</div>
        </div>
    </div>`; 

    let resolvedAnim = getAnimacao(cena, idx);
    let isResolvedZoom = (resolvedAnim === 'zoom_in' || resolvedAnim === 'zoom_out');
    let isResolvedParada = (resolvedAnim === 'nenhuma');

    html += `
    <div class="info-box" style="padding:0; overflow:hidden;">
        <div class="advanced-header" onclick="toggleAdvancedMenu()">
            <i id="advIcon" class="ph-fill ph-caret-${window._advMenuOpen ? 'down' : 'right'}"></i> Avançado
        </div>
        <div id="advContent" class="advanced-content" style="display: ${window._advMenuOpen ? 'block' : 'none'};">`;
    
    if (isResolvedZoom) {
        let zoomVal = cena.zoom_intensity !== undefined ? cena.zoom_intensity : 0.15;
        html += `
            <label style="font-size:0.75rem; margin-top:0;">Intensidade do Zoom:</label>
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:5px;">
                <input type="range" id="zoomSlider" min="0.01" max="1.0" step="0.01" value="${Math.min(zoomVal, 1.0)}" oninput="onZoomSliderChange(${idx}, this.value)" onchange="pushHistory()" style="flex:1;">
                <span id="zoomLabel" style="cursor:ns-resize; font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:40px; text-align:right;" onmousedown="startDragZoom(event, ${idx})">${(zoomVal * 100).toFixed(0)}%</span>
            </div>
            <label style="font-size:0.7rem; color:var(--text-muted); display:flex; align-items:center; gap:5px; margin-bottom:15px; text-transform:none;">
                <input type="checkbox" id="zoomGlobalCheck"> Para todas as cenas
            </label>
        `;
    }

    if (!isResolvedParada) {
        let aStart = cena.anim_start !== undefined ? cena.anim_start : 0.0;
        let aEnd = cena.anim_end !== undefined ? cena.anim_end : 1.0;
        let easing = cena.anim_easing || 'linear';

        html += `
            <label style="font-size:0.75rem;">Tempo da Animação:</label>
            <div style="display:flex; flex-direction:column; gap:5px; margin-bottom:5px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:0.7rem; color:var(--text-muted); width:30px;">Início</span>
                    <input type="range" id="animStart" min="0" max="100" value="${aStart*100}" oninput="updateAnimTiming(${idx})" onchange="pushHistory()" style="flex:1;">
                </div>
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:0.7rem; color:var(--text-muted); width:30px;">Fim</span>
                    <input type="range" id="animEnd" min="0" max="100" value="${aEnd*100}" oninput="updateAnimTiming(${idx})" onchange="pushHistory()" style="flex:1;">
                </div>
            </div>
            
            <label style="font-size:0.75rem; margin-top:10px;">Suavização (Easing):</label>
            <div class="select-wrapper-native" style="margin-bottom:5px;">
                <select id="animEasing" onchange="updateAnimEasing(${idx}, this.value)">
                    <option value="linear" ${easing==='linear'?'selected':''}>Linear</option>
                    <option value="suave" ${easing==='suave'?'selected':''}>Suave</option>
                    <option value="dinamica" ${easing==='dinamica'?'selected':''} ${isResolvedZoom ? '' : 'disabled'}>Dinâmica</option>
                </select>
            </div>
            <label style="font-size:0.7rem; color:var(--text-muted); display:flex; align-items:center; gap:5px; margin-bottom:15px; text-transform:none;">
                <input type="checkbox" id="animGlobalCheck"> Para todas as cenas
            </label>
        `;
    }

    let tVol = cena.transition_volume !== undefined ? cena.transition_volume : 1.0;
    let tLocal = cena.trans_vol_local || false;
    html += `
        <label style="font-size:0.75rem;">Volume da Transição:</label>
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:5px;">
            <input type="range" id="transVolSlider" min="0" max="3" step="0.05" value="${tVol}" oninput="updateTransVol(${idx}, this.value)" onchange="pushHistory()" style="flex:1;">
            <span id="transVolLabel" style="font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:40px; text-align:right;">${(tVol*100).toFixed(0)}%</span>
        </div>
        <label style="font-size:0.7rem; color:var(--text-muted); display:flex; align-items:center; gap:5px; text-transform:none;">
            <input type="checkbox" id="transLocalCheck" ${tLocal ? 'checked':''} onchange="updateTransVolLocal(${idx}, this.checked)"> Apenas para esta cena
        </label>
    </div></div>`; 

    let isVideoTarget = cena.arquivo_origem && /\.(mp4|webm|ogg|mov|mkv|avi)$/i.test(cena.arquivo_origem);
    if (isVideoTarget) {
        let vVol = cena.volume_video !== undefined ? cena.volume_video : 1.0;
        html += `
        <div class="info-box" style="margin-top: 15px;">
            <label><i class="ph-fill ph-speaker-high"></i> Volume do Vídeo:</label>
            <div style="display:flex; align-items:center; gap:10px; margin-top:5px;">
                <input type="range" id="videoVolSlider" min="0" max="2" step="0.05" value="${vVol}" oninput="updateVideoVol(${idx}, this.value)" onchange="pushHistory()" style="flex:1;">
                <span id="videoVolLabel" style="font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:40px; text-align:right;">${(vVol*100).toFixed(0)}%</span>
            </div>
        </div>`;
    }

    html += `<div style="margin-top: 15px;"><button class="btn-danger" onclick="itemClicadoMenu=${idx}; removerCenaSelecionada(true)"><i class="ph ph-trash"></i> Remover Cena</button></div>`;
    document.getElementById('painelProps').innerHTML = html; 
}

async function acionarUpscaleCena() {
    if (itemClicadoMenu === null) return; document.getElementById('menuContexto').style.display = 'none';
    document.getElementById('painelProps').innerHTML = `<p style="color:var(--primary-purple);"><i class="ph ph-spinner-gap"></i> Aplicando IA na imagem...</p>`;
    await fetch('/api/melhorar_imagem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id_cena: itemClicadoMenu }) });
    delete imageCache[itemClicadoMenu]; carregarImagensNaMemoria(); carregarBiblioteca(); atualizarPainel(itemClicadoMenu); pushHistory();
}

let upscaleInterval = null; let upscaleStartTime = 0;
async function iniciarUpscaleLote() {
    document.getElementById('modalProgressos').style.display = 'flex';
    document.getElementById('progResultArea').style.display = 'none';
    document.getElementById('progBar').style.width = '0%'; 
    document.getElementById('progBar').className = 'progress-fill purple';
    document.getElementById('progTitle').innerHTML = "<i class='ph ph-sparkle' style='color:var(--primary-purple)'></i> Melhorando Todas as Imagens...";
    upscaleStartTime = Date.now();
    try { const res = await fetch('/api/melhorar_todas', { method: 'POST' }); const dados = await res.json(); if(dados.task_id) upscaleInterval = setInterval(() => checarStatusUpscale(dados.task_id), 1000); } catch(e) { alert("Erro de rede."); fecharModalProgressos(); }
}

async function checarStatusUpscale(taskId) {
    try {
        const res = await fetch(`/api/status_upscale/${taskId}`); const status = await res.json();
        let decorrido = (Date.now() - upscaleStartTime) / 1000; let progresso = status.progresso || 0;
        document.getElementById('progBar').style.width = `${progresso}%`;
        if (progresso > 0 && progresso < 100) { let eta = (decorrido / (progresso / 100)) - decorrido; document.getElementById('progStatusText').innerText = `Aprimorando: ${status.atual}/${status.total} fotos`; document.getElementById('progTimeStats').innerText = `${formatTimeNormal(decorrido)} | ETA: ${formatTimeNormal(eta)}`; }
        if (status.estado === 'concluido') { clearInterval(upscaleInterval); imageCache = {}; carregarImagensNaMemoria(); carregarBiblioteca(); fecharModalProgressos(); } else if (status.estado === 'erro') { clearInterval(upscaleInterval); alert("Erro no servidor de IA."); fecharModalProgressos(); }
    } catch(e) {}
}

let renderInterval = null; let renderStartTime = 0;
async function iniciarRenderBackend() {
    if(isPlaying) togglePlay();
    const nomeStr = document.getElementById('inputNomeArquivo').value; const resStr = document.getElementById('inputResolucao').value; const fpsStr = document.getElementById('inputFPS').value;
    fecharModalPreRender();
    document.getElementById('modalProgressos').style.display = 'flex'; document.getElementById('progResultArea').style.display = 'none'; document.getElementById('progArea').style.display = 'block'; 
    document.getElementById('progBar').style.width = '0%'; 
    document.getElementById('progBar').className = 'progress-fill';
    document.getElementById('progTitle').innerHTML = "<i class='ph ph-export' style='color:var(--primary-cyan)'></i> Renderizando Vídeo..."; document.getElementById('progDesc').innerText = "O Servidor Python e a GPU estão forjando seu projeto.";
    renderStartTime = Date.now();
    
    let payload = { projeto: projetoAtual, nome_arquivo: nomeStr, fps: parseInt(fpsStr), resolucao: resStr === "9:16" ? [1080, 1920] : [1920, 1080] };
    try { const res = await fetch('/api/renderizar_final', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); const dados = await res.json(); if(dados.task_id) renderInterval = setInterval(() => checarStatusRender(dados.task_id), 1000); } catch (e) { alert("Erro ao iniciar o Render."); fecharModalProgressos(); }
}

async function checarStatusRender(taskId) {
    try {
        const res = await fetch(`/api/status_render/${taskId}`); const status = await res.json();
        let decorrido = (Date.now() - renderStartTime) / 1000; let progresso = status.progresso || 0;
        document.getElementById('progBar').style.width = `${progresso}%`;
        if (progresso > 0 && progresso < 100) { let eta = (decorrido / (progresso / 100)) - decorrido; document.getElementById('progStatusText').innerText = `Comprimindo frame ${status.frame_atual}/${status.total_frames} (${status.fps} fps)`; document.getElementById('progTimeStats').innerText = `${formatTimeNormal(decorrido)} | ETA: ${formatTimeNormal(eta)}`; }
        if (status.estado === 'concluido') { clearInterval(renderInterval); mostrarVideoPronto(status.url_video); } else if (status.estado === 'erro') { clearInterval(renderInterval); alert("Erro na renderização."); fecharModalProgressos(); }
    } catch(e) {}
}

let previewAudioElement = new Audio();
let musicaSelecionadaModal = null;
let indexFaixaEditando = null; 

previewAudioElement.addEventListener('timeupdate', () => {
    let slider = document.getElementById('previewAudioSlider');
    let timeLabel = document.getElementById('previewAudioTime');
    if (previewAudioElement.duration) {
        let percent = (previewAudioElement.currentTime / previewAudioElement.duration) * 100;
        slider.value = percent;
        timeLabel.innerText = `${formatTimeNormal(previewAudioElement.currentTime)} / ${formatTimeNormal(previewAudioElement.duration)}`;
    }
});

previewAudioElement.addEventListener('ended', () => {
    document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-play"></i>';
});

const coresClimas = ['#06b6d4', '#ec4899', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#3b82f6', '#f97316', '#14b8a6'];
function gerarCorClima(str) {
    let hash = 0; for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
    return coresClimas[Math.abs(hash) % coresClimas.length];
}

async function abrirModalSubstituirMusica(idxFaixa) {
    indexFaixaEditando = idxFaixa;
    document.getElementById('modalSubstituirMusica').style.display = 'flex';
    document.getElementById('listaMusicasModal').innerHTML = '<div style="text-align:center; padding: 40px;"><div class="spinner-carregando"></div><p style="margin-top:15px; color:var(--text-muted);">Sincronizando biblioteca...</p></div>';
    
    previewAudioElement.pause(); previewAudioElement.src = "";
    document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-play"></i>';
    document.getElementById('previewAudioTitle').innerText = "Nenhuma faixa selecionada";
    document.getElementById('previewAudioArtist').innerText = "--";
    document.getElementById('btnImportarMusica').disabled = true;

    try {
        const res = await fetch('/api/musicas_biblioteca');
        const musicas = await res.json();
        
        let html = '';
        let climasEncontrados = new Set(); 

        if (musicas.length === 0) {
            html = '<p style="text-align:center; color:var(--text-muted); margin-top:30px;">Nenhuma música encontrada nas pastas.</p>';
        } else {
            musicas.forEach((m, i) => {
                let min = Math.floor(m.duracao / 60);
                let sec = Math.floor(m.duracao % 60).toString().padStart(2, '0');
                let climaSeguro = m.clima || 'Sem Clima';
                climasEncontrados.add(climaSeguro);
                
                let nomeLimpo = (m.titulo || "").replace(/\.(mp3|wav|ogg|m4a)$/i, '');
                let tituloFatiado = nomeLimpo;
                let artistaFatiado = "Desconhecido";
                let bpmFatiado = "-- BPM";

                let bpmMatch = nomeLimpo.match(/_?(\d+)bpm/i);
                if (bpmMatch) {
                    bpmFatiado = bpmMatch[1] + " BPM";
                    nomeLimpo = nomeLimpo.replace(bpmMatch[0], ''); 
                }

                if (nomeLimpo.includes(' - ')) {
                    let partes = nomeLimpo.split(' - ');
                    tituloFatiado = partes[0].trim();
                    artistaFatiado = partes.slice(1).join(' - ').replace(/_$/, '').trim();
                } else {
                    tituloFatiado = nomeLimpo.replace(/_$/, '').trim();
                }

                let fullTitleSafe = tituloFatiado.replace(/'/g, "\\'").replace(/"/g, "&quot;");
                let fullArtistSafe = artistaFatiado.replace(/'/g, "\\'").replace(/"/g, "&quot;");
                let caminhoEscapado = m.caminho.replace(/'/g, "\\'").replace(/"/g, "&quot;");
                let corTag = gerarCorClima(climaSeguro);
                
                html += `
                <div class="music-item" id="music_item_${i}" data-titulo="${fullTitleSafe}" data-clima="${climaSeguro}" onclick="selecionarMusicaPreview(${i}, '${caminhoEscapado}', '${fullTitleSafe}', '${fullArtistSafe}', '${climaSeguro}', ${m.duracao || 0})">
                    <div class="play-col"><i class="ph-fill ph-play-circle"></i></div>
                    <div class="title-col">${tituloFatiado}</div>
                    <div class="artist-col">${artistaFatiado}</div>
                    <div><span class="music-tag" style="background-color: ${corTag};">${climaSeguro}</span></div>
                    <div class="dur-col"><i class="ph ph-clock"></i> ${min}:${sec}</div>
                    <div class="bpm-col">${bpmFatiado}</div>
                </div>`;
            });
        }
        document.getElementById('listaMusicasModal').innerHTML = html;

        let selectFiltro = document.getElementById('filtroClimaAudio');
        if (selectFiltro) {
            let opcoesHTML = '<option value="todos">Todos os Climas</option>';
            Array.from(climasEncontrados).sort().forEach(clima => { opcoesHTML += `<option value="${clima.toLowerCase()}">${clima}</option>`; });
            selectFiltro.innerHTML = opcoesHTML;
        }
    } catch (e) {
        document.getElementById('listaMusicasModal').innerHTML = '<p style="color:red; text-align:center;">Erro ao carregar músicas.</p>';
    }
}

window.selecionarMusicaPreview = function(indexDOM, caminho, titulo, artista, clima, duracao) {
    document.querySelectorAll('.music-item').forEach(el => el.classList.remove('selected'));
    document.getElementById(`music_item_${indexDOM}`).classList.add('selected');
    
    musicaSelecionadaModal = { caminho, titulo, clima, duracao }; 
    
    document.getElementById('previewAudioTitle').innerText = titulo;
    document.getElementById('previewAudioArtist').innerText = artista;
    document.getElementById('btnImportarMusica').disabled = false;
    
    previewAudioElement.src = "/" + caminho;
    previewAudioElement.play();
    document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-pause"></i>';
};

window.abrirModalNovaMusica = function() {
    indexFaixaEditando = 'nova'; 
    abrirModalSubstituirMusica('nova');
};

window.removerTodasMusicas = function() {
    if(confirm("Tem certeza que deseja limpar TODA a trilha sonora?")) {
        if(projetoAtual.faixas_musicais) {
            projetoAtual.faixas_musicais.forEach((f, idx) => {
                if(f) itemsDataset.remove(`musica_${idx}`);
            });
            projetoAtual.faixas_musicais = [];
        }
        sincronizarJSON();
        pushHistory();
        itemClicadoMenu = null;
        cenaAtivaPropriedades = -1;
        document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`;
        AudioEngine.pararTudo();
        AudioEngine.inicializar();
    }
};

function togglePreviewAudio() {
    if (previewAudioElement.paused && previewAudioElement.src) {
        previewAudioElement.play();
        document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-pause"></i>';
    } else {
        previewAudioElement.pause();
        document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-play"></i>';
    }
}

function seekPreviewAudio(percent) {
    if (previewAudioElement.duration) {
        previewAudioElement.currentTime = (percent / 100) * previewAudioElement.duration;
    }
}

async function uploadNovaMusica(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    document.getElementById('listaMusicasModal').innerHTML = '<div style="text-align:center; padding: 40px;"><div class="spinner-carregando" style="border-top-color:var(--primary-purple);"></div><p style="margin-top:15px; color:var(--text-main);">Enviando e processando áudio na nuvem...</p></div>';
    
    try {
        const res = await fetch('/api/upload_musica', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.status === 'ok') {
            // Recarrega a biblioteca do servidor
            await abrirModalSubstituirMusica(indexFaixaEditando);
            
            // INJEÇÃO: Varre a DOM buscando a música que acabou de chegar e clica nela automaticamente
            setTimeout(() => {
                let itens = document.querySelectorAll('.music-item');
                for(let el of itens) {
                    if(el.getAttribute('data-titulo') === data.titulo) {
                        el.click(); // Destrava o botão OK e carrega o preview
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        break;
                    }
                }
            }, 500); // Aguarda o HTML ser desenhado
        }
    } catch (e) {
        alert("Erro ao enviar a música.");
        abrirModalSubstituirMusica(indexFaixaEditando);
    }
}

window.fecharModalMusica = function() {
    document.getElementById('modalSubstituirMusica').style.display = 'none';
    
    if (typeof previewAudioElement !== 'undefined' && !previewAudioElement.paused) {
        previewAudioElement.pause();
        document.getElementById('btnPlayPreviewAudio').innerHTML = '<i class="ph-fill ph-play"></i>';
    }
};

window.confirmarSubstituicaoMusica = async function() {
    if (!musicaSelecionadaModal || indexFaixaEditando === null) return;
    
    if (indexFaixaEditando === 'nova') {
        if (!projetoAtual.faixas_musicais) projetoAtual.faixas_musicais = [];
        
        let tempoAgulha = dateToSeg(timeline.getCustomTime('agulha'));
        let duracaoAudio = musicaSelecionadaModal.duracao > 0 ? musicaSelecionadaModal.duracao : (previewAudioElement.duration || 30);
        let novoIndex = projetoAtual.faixas_musicais.length;
        
        let novaFaixa = {
            arquivo: musicaSelecionadaModal.caminho,
            titulo: musicaSelecionadaModal.titulo,
            clima: musicaSelecionadaModal.clima,
            inicio: tempoAgulha,
            fim: tempoAgulha + duracaoAudio,
            volume: 0.15,
            fade_in: 1.5,
            fade_out: 1.5
        };
        
        projetoAtual.faixas_musicais.push(novaFaixa);
        
        itemsDataset.add({
            id: `musica_${novoIndex}`, group: 'a2', className: 'music-clip',
            content: `
                <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                    <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                        <i class="ph-fill ph-music-notes"></i> ${novaFaixa.titulo}
                    </div>
                    <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none;">
                        <canvas class="waveform-music-canvas" data-idx="${novoIndex}" style="width: 100%; height: 100%; display: block;"></canvas>
                    </div>
                </div>
            `,
            start: segToDate(novaFaixa.inicio), end: segToDate(novaFaixa.fim),
            editable: { updateTime: true, updateGroup: false, remove: false }
        });
    } else {
        let faixa = projetoAtual.faixas_musicais[indexFaixaEditando];
        faixa.arquivo = musicaSelecionadaModal.caminho;
        faixa.titulo = musicaSelecionadaModal.titulo;
        faixa.clima = musicaSelecionadaModal.clima;
        
        let dsItem = itemsDataset.get(`musica_${indexFaixaEditando}`);
        if (dsItem) {
            dsItem.content = `
                <div style="width: 100%; height: 100%; display: flex; flex-direction: column; position: relative;">
                    <div style="font-size: 11px; font-weight: 600; color: white; padding: 2px 8px; z-index: 2; position: absolute; text-shadow: 0px 1px 3px rgba(0,0,0,0.8);">
                        <i class="ph-fill ph-music-notes"></i> ${faixa.titulo}
                    </div>
                    <div class="waveform-container" style="position: absolute; top:0; left:0; right:0; bottom:0; pointer-events: none;">
                        <canvas class="waveform-music-canvas" data-idx="${indexFaixaEditando}" style="width: 100%; height: 100%; display: block;"></canvas>
                    </div>
                </div>
            `;
            itemsDataset.update(dsItem);
        }
    }
    
    sincronizarJSON();
    pushHistory();
    
    if (indexFaixaEditando !== 'nova') {
        atualizarPainelMusica(indexFaixaEditando);
    }
    
    fecharModalMusica();
    
    // >>> FIX: Aguarda o motor decodificar o MP3 antes de mandar pintar a tela
    await AudioEngine.inicializar(); 
    setTimeout(() => {
        if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas();
    }, 100);
};

function removerMusicaSelecionada(idx) {
    if(confirm("Remover esta faixa de áudio da timeline?")) {
        itemsDataset.remove(`musica_${idx}`);
        if(projetoAtual.faixas_musicais) {
            projetoAtual.faixas_musicais[idx] = null; 
        }
        sincronizarJSON();
        pushHistory();
        itemClicadoMenu = null;
        cenaAtivaPropriedades = -1;
        document.getElementById('painelProps').innerHTML = `<h3>Propriedades</h3><p style="color:var(--text-muted); font-size:0.85em;">A reprodução guiará este painel.</p>`;
    }
}

window.atualizarAtributoMusica = function(idx, atributo, valor) {
    projetoAtual.faixas_musicais[idx][atributo] = parseFloat(valor);
    sincronizarJSON(); 
    pushHistory();
    
    if(atributo === 'volume') {
        let lbl = document.getElementById(`volMusicaLabel_${idx}`);
        if(lbl) lbl.innerText = (parseFloat(valor) * 100).toFixed(0) + '%';
        
        if(typeof AudioEngine !== 'undefined' && AudioEngine.bgmGains && AudioEngine.bgmGains[idx]) {
            AudioEngine.bgmGains[idx].gain.value = parseFloat(valor);
        }
    } else if (atributo === 'fade_in') {
        let lbl = document.getElementById(`fadeInLabel_${idx}`);
        if(lbl) lbl.innerText = parseFloat(valor).toFixed(1) + 's';
    } else if (atributo === 'fade_out') {
        let lbl = document.getElementById(`fadeOutLabel_${idx}`);
        if(lbl) lbl.innerText = parseFloat(valor).toFixed(1) + 's';
    }
    
    if(window.desenharWaveformsMusicas) window.desenharWaveformsMusicas(); 
};

window.atualizarPainelMusica = function(idxFaixa) {
    if (!projetoAtual.faixas_musicais || !projetoAtual.faixas_musicais[idxFaixa]) return;
    
    let faixa = projetoAtual.faixas_musicais[idxFaixa];
    let volAtual = faixa.volume !== undefined ? faixa.volume : 0.15;
    let fadeInAtual = faixa.fade_in !== undefined ? faixa.fade_in : 1.5;
    let fadeOutAtual = faixa.fade_out !== undefined ? faixa.fade_out : 1.5;

    let html = `
    <div class="prop-header">
        <span>Faixa Sonora</span>
        <span style="color:var(--primary-purple); font-weight:bold;">${faixa.clima || 'Personalizado'}</span>
    </div>
    
    <div class="info-box">
        <label><i class="ph-fill ph-speaker-high"></i> Volume Relativo:</label>
        <div style="display:flex; align-items:center; gap: 10px; margin-top: 5px;">
            <input type="range" min="0" max="1" step="0.01" value="${volAtual}" 
                   oninput="atualizarAtributoMusica(${idxFaixa}, 'volume', this.value)" style="flex:1;">
            <span id="volMusicaLabel_${idxFaixa}" style="font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:40px; text-align:right;">${(volAtual * 100).toFixed(0)}%</span>
        </div>
    </div>
    
    <div class="info-box">
        <label><i class="ph ph-sliders-horizontal"></i> Transições de Áudio (Fades):</label>
        <div style="display:flex; flex-direction:column; gap:10px; margin-top: 5px;">
            
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:0.75rem; color:var(--text-muted); width:55px;">Fade-In</span>
                <input type="range" min="0" max="10" step="0.1" value="${fadeInAtual}" 
                       oninput="atualizarAtributoMusica(${idxFaixa}, 'fade_in', this.value)" style="flex:1;">
                <span id="fadeInLabel_${idxFaixa}" style="font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:35px; text-align:right;">${parseFloat(fadeInAtual).toFixed(1)}s</span>
            </div>
            
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:0.75rem; color:var(--text-muted); width:55px;">Fade-Out</span>
                <input type="range" min="0" max="10" step="0.1" value="${fadeOutAtual}" 
                       oninput="atualizarAtributoMusica(${idxFaixa}, 'fade_out', this.value)" style="flex:1;">
                <span id="fadeOutLabel_${idxFaixa}" style="font-family:monospace; font-weight:bold; color:var(--primary-cyan); min-width:35px; text-align:right;">${parseFloat(fadeOutAtual).toFixed(1)}s</span>
            </div>
            
        </div>
    </div>`;
    
    document.getElementById('painelProps').innerHTML = html;
};

window.filtrarBibliotecaAudio = function() {
    const limparTexto = (texto) => (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

    let termoBusca = limparTexto(document.getElementById('buscaAudio').value);
    let filtroClima = limparTexto(document.getElementById('filtroClimaAudio').value);
    
    let containerLista = document.getElementById('listaMusicasModal');
    if(!containerLista) return;
    
    let itens = containerLista.children;
    
    for(let i = 0; i < itens.length; i++) {
        let item = itens[i];
        
        let titulo = limparTexto(item.getAttribute('data-titulo'));
        let clima = limparTexto(item.getAttribute('data-clima'));
        
        let passouBusca = termoBusca === "" || titulo.includes(termoBusca) || clima.includes(termoBusca);
        let passouClima = filtroClima === "todos" || clima.includes(filtroClima);
        
        if (passouBusca && passouClima) {
            item.style.display = ""; 
        } else {
            item.style.display = "none";
        }
    }
};

window.abrirModalPreRender = function() {
    try {
        let isVertical = false; 
        let form = (projetoAtual && projetoAtual.formato) ? String(projetoAtual.formato).toLowerCase() : "";
        if (form.includes('short') || form.includes('vertical') || form.includes('tiktok')) isVertical = true;
        if (projetoAtual && Array.isArray(projetoAtual.resolucao) && projetoAtual.resolucao.length >= 2) {
            if (projetoAtual.resolucao[0] < projetoAtual.resolucao[1]) isVertical = true;
        }
        document.getElementById('inputResolucao').value = isVertical ? "9:16" : "16:9";
        document.getElementById('modalPreRender').style.display = 'flex';
    } catch(e) {
        console.error("Erro ignorado ao ler formato:", e);
        document.getElementById('inputResolucao').value = "16:9";
        document.getElementById('modalPreRender').style.display = 'flex';
    }
};

window.fecharModalPreRender = function() { 
    document.getElementById('modalPreRender').style.display = 'none'; 
};

window.fecharModalProgressos = function() {
    document.getElementById('modalProgressos').style.display = 'none';
};

window.mostrarVideoPronto = function(url) {
    document.getElementById('progArea').style.display = 'none';
    document.getElementById('progResultArea').style.display = 'block';
    document.getElementById('progTitle').innerHTML = "<i class='ph-fill ph-check-circle' style='color:#10b981'></i> Vídeo Concluído!";
    
    let player = document.getElementById('finalVideoPlayer');
    player.src = url;
    player.load();
    
    document.getElementById('btnDownloadFinal').href = url;
};

window.onload = inicializar;
