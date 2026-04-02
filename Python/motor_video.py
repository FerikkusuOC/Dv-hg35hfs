import os
import time
import platform
import numpy as np
import moderngl
import subprocess
from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoFileClip
import moviepy.audio.fx.all as afx
from PIL import Image, ImageOps

from configuracoes import RESOLUCAO as RES_PADRAO

SISTEMA = platform.system()

# ==========================================
# CAÇADOR DE FFMPEG E PROBE DE CODEC
# ==========================================
if SISTEMA == "Windows":
    CAMINHO_FFMPEG = "ffmpeg.exe"
    if not os.path.exists(CAMINHO_FFMPEG):
        import imageio_ffmpeg
        CAMINHO_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
else:
    import shutil
    CAMINHO_FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"

def checar_suporte_nvenc(ffmpeg_path):
    """Verifica se o FFmpeg local foi compilado com suporte a aceleração NVIDIA."""
    try:
        res = subprocess.run([ffmpeg_path, '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in res.stdout
    except:
        return False

# Trava de segurança: Se não tiver NVENC (ex: Colab ou AMD), usa CPU (libx264)
CODEC_VIDEO = "h264_nvenc" if checar_suporte_nvenc(CAMINHO_FFMPEG) else "libx264"
if CODEC_VIDEO == "libx264":
    print("  [MOTOR DE VÍDEO] NVENC indisponível. Fallback de segurança para libx264 (CPU) ativado.")

PASTA_IMAGENS = os.path.abspath("imagens_finais")
PASTA_UPSCALE = os.path.join(PASTA_IMAGENS, "upscale")
PASTA_MIDIA = os.path.abspath("midia_projeto")

VERTEX_SHADER = '''
#version 330
in vec2 in_vert;
in vec2 in_texcoord;
out vec2 uv;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); uv = in_texcoord; }
'''

VERTICES_PADRAO = np.array([
    -1.0, -1.0,  0.0, 0.0,
     1.0, -1.0,  1.0, 0.0,
    -1.0,  1.0,  0.0, 1.0,
     1.0,  1.0,  1.0, 1.0,
], dtype='f4')

COLECAO_TRANSICOES = {
    "zoom_rotacao": {
        "audio": "zoom_de_rotacao.mp3", "ancora_frames": 10,
        "fragment": '''
            #version 330
            uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
            in vec2 uv; out vec4 f_color;
            const float PI = 3.14159265359;
            float easeInOutCubic(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }
            vec2 rotate_and_scale(vec2 p, float angle, float scale) { vec2 centered = p - 0.5; float s = sin(angle); float c = cos(angle); vec2 rotated = vec2(centered.x * c - centered.y * s, centered.x * s + centered.y * c); return (rotated / scale) + 0.5; }
            void main() {
                float ease = easeInOutCubic(progress);
                float angle_from = ease * -PI; float scale_from = 1.0 + ease * 4.0; vec2 uv_from = rotate_and_scale(uv, angle_from, scale_from);
                float angle_to = (ease - 1.0) * -PI; float scale_to = 1.0 + (1.0 - ease) * 4.0; vec2 uv_to = rotate_and_scale(uv, angle_to, scale_to);
                vec4 color_from = texture(tex_from, uv_from); vec4 color_to = texture(tex_to, uv_to);
                if(uv_from.x < 0.0 || uv_from.x > 1.0 || uv_from.y < 0.0 || uv_from.y > 1.0) color_from = vec4(0.0);
                if(uv_to.x < 0.0 || uv_to.x > 1.0 || uv_to.y < 0.0 || uv_to.y > 1.0) color_to = vec4(0.0);
                float mix_factor = smoothstep(0.4, 0.6, progress); f_color = mix(color_from, color_to, mix_factor);
            }
        '''
    },
    "zoom_suave_paralaxe": {
        "audio": "zoom_suave_paralaxe.mp3", "ancora_frames": 13,
        "fragment": '''
            #version 330
            uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
            in vec2 uv; out vec4 f_color;
            float easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }
            vec2 apply_spherical_bulge(vec2 p, float intensity) { vec2 d = p - 0.5; float dist = length(d); float radius = 1.0; if (dist > 0.0 && dist < radius) { float percent = dist / radius; float new_percent = pow(percent, 1.0 + intensity); return 0.5 + (d / percent) * new_percent * radius; } return p; }
            void main() {
                float ease = easeInOutQuint(progress);
                float bulge_from = ease * 3.0; vec2 uv_from = apply_spherical_bulge(uv, bulge_from); float zoom_A = mix(1.0, 0.02, ease); uv_from = 0.5 + (uv_from - 0.5) * zoom_A;
                float bulge_to = (1.0 - ease) * 3.0; vec2 uv_to = apply_spherical_bulge(uv, bulge_to); float zoom_B = mix(0.02, 1.0, ease); uv_to = 0.5 + (uv_to - 0.5) * zoom_B;
                vec4 color_from = texture(tex_from, uv_from); vec4 color_to = texture(tex_to, uv_to);
                if(uv_from.x < 0.0 || uv_from.x > 1.0 || uv_from.y < 0.0 || uv_from.y > 1.0) color_from = vec4(0.0); if(uv_to.x < 0.0 || uv_to.x > 1.0 || uv_to.y < 0.0 || uv_to.y > 1.0) color_to = vec4(0.0);
                float mix_factor = smoothstep(0.45, 0.55, progress); f_color = mix(color_from, color_to, mix_factor);
            }
        '''
    },
    "warp_zoom": {
        "audio": "warp_zoom.mp3", "ancora_frames": 10,
        "fragment": '''
            #version 330
            uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
            in vec2 uv; out vec4 f_color;
            float easeInOutQuart(float t) { return t < 0.5 ? 8.0 * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 4.0) / 2.0; }
            vec2 mirrored_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }
            vec4 warp_sample(sampler2D tex, vec2 p, float scale, float blur_strength) { vec2 center = vec2(0.5); vec2 dir = (p / scale + center * (1.0 - 1.0/scale)) - center; vec4 color = vec4(0.0); const int SAMPLES = 24; for (int i = 0; i < SAMPLES; i++) { float f = float(i) / float(SAMPLES - 1); vec2 shifted_uv = center + dir * (1.0 + f * blur_strength); color += texture(tex, mirrored_uv(shifted_uv)); } return color / float(SAMPLES); }
            void main() {
                float ease = easeInOutQuart(progress);
                float scale_A = mix(1.0, 12.0, ease); float blur_A = ease * 1.2; vec4 color_from = warp_sample(tex_from, uv, scale_A, blur_A);
                float scale_B = mix(0.01, 1.0, ease); float blur_B = (1.0 - ease) * 1.2; vec4 color_to = warp_sample(tex_to, uv, scale_B, blur_B);
                float mix_factor = smoothstep(0.4, 0.6, progress); f_color = mix(color_from, color_to, mix_factor);
            }
        '''
    },
    "buraco_de_minhoca": {
        "audio": "buraco_de_minhoca.mp3", "ancora_frames": 17, 
        "fragment": '''
            #version 330
            uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
            in vec2 uv; out vec4 f_color;
            const float PI = 3.14159265359;
            float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
            float easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }
            vec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }
            void main() {
                float ease = easeInOutQuint(progress);
                float peak_mask = sin(progress * PI); float shake_time = floor(progress * 150.0); vec2 shake = vec2(hash(vec2(shake_time, 1.0)), hash(vec2(shake_time, 2.0))) - 0.5; shake *= 0.15 * peak_mask; vec2 centerA = vec2(0.5) + shake; vec2 dirA = uv - centerA; float blur_strengthA = peak_mask * 1.2; float scaleA = mix(1.0, 25.0, ease);
                float pB = clamp((progress - 0.5) * 2.0, 0.0, 1.0); float easeOutB = 1.0 - pow(1.0 - pB, 5.0); vec2 centerB = vec2(0.5); vec2 dirB = uv - centerB; float r2 = dot(dirB, dirB); float concave_amount = mix(25.0, 0.0, easeOutB); vec2 distorted_dirB = dirB * (1.0 + concave_amount * r2); float scaleB = mix(0.03, 1.0, easeOutB); float blur_strengthB = mix(2.0, 0.0, easeOutB);
                float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; float current_scaleA = scaleA * (1.0 + f * blur_strengthA); vec2 sampleA = centerA + dirA / current_scaleA; vec4 colA = texture(tex_from, wrap_uv(sampleA)); float current_scaleB = scaleB * (1.0 + f * blur_strengthB); vec2 sampleB = centerB + distorted_dirB / current_scaleB; vec4 colB = texture(tex_to, wrap_uv(sampleB)); color += mix(colA, colB, smoothstep(0.45, 0.55, progress)); }
                f_color = color / float(SAMPLES);
            }
        '''
    }
}

FRAGMENT_OLHO_PEIXE = '''
    #version 330
    uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
    in vec2 uv; out vec4 f_color;
    const float PI = 3.14159265359; const vec2 DIR = vec2({DIR_X}, {DIR_Y});
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    float easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }
    vec2 apply_barrel(vec2 p, float amount) { vec2 d = (p - 0.5); float d_len = length(d); return 0.5 + (d * (1.0 + amount * (d_len * d_len))); }
    vec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }
    void main() {
        float ease = easeInOutQuint(progress); float bulge_amount = 2.5 * sin(progress * PI); vec2 distorted_uv = apply_barrel(uv, bulge_amount); vec2 offset = ease * 4.0 * DIR; float blur_mask = smoothstep(0.25, 0.45, progress) * (1.0 - smoothstep(0.55, 0.75, progress)); float blur_amount = blur_mask * 0.8; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 sample_uv = distorted_uv - offset + DIR * (f * blur_amount); color += mix(texture(tex_from, wrap_uv(sample_uv)), texture(tex_to, wrap_uv(sample_uv)), smoothstep(0.4, 0.6, progress)); } f_color = color / float(SAMPLES);
    }
'''
for nome, (dx, dy) in {"rolagem_olho_de_peixe_baixo": (0.0, -1.0), "rolagem_olho_de_peixe_cima": (0.0, 1.0), "rolagem_olho_de_peixe_direita": (1.0, 0.0), "rolagem_olho_de_peixe_esquerda": (-1.0, 0.0), "rolagem_olho_de_peixe_baixo_direita": (1.0, -1.0), "rolagem_olho_de_peixe_baixo_esquerda": (-1.0, -1.0), "rolagem_olho_de_peixe_cima_direita": (1.0, 1.0), "rolagem_olho_de_peixe_cima_esquerda": (-1.0, 1.0)}.items():
    COLECAO_TRANSICOES[nome] = {"audio": "rolagem_olho_de_peixe.mp3", "ancora_frames": 20, "fragment": FRAGMENT_OLHO_PEIXE.replace("{DIR_X}", str(dx)).replace("{DIR_Y}", str(dy))}

FRAGMENT_LIMPEZA_RAPIDA = '''
    #version 330
    uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
    in vec2 uv; out vec4 f_color;
    const float PI = 3.14159265359; const vec2 DIR = vec2({DIR_X}, {DIR_Y});
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    float easeInOutQuint(float t) { return t < 0.5 ? 16.0 * t * t * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 5.0) / 2.0; }
    void main() {
        float p = clamp((progress - 0.15) / 0.70, 0.0, 1.0); float ease = easeInOutQuint(p); vec2 offset = ease * DIR; float blur_amount = sin(p * PI) * 0.6; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 sample_uv = uv + DIR * (f * blur_amount); vec2 uvA = sample_uv - offset; vec2 uvB = uvA + DIR; bool inA = (uvA.x >= 0.0 && uvA.x <= 1.0 && uvA.y >= 0.0 && uvA.y <= 1.0); bool inB = (uvB.x >= 0.0 && uvB.x <= 1.0 && uvB.y >= 0.0 && uvB.y <= 1.0); color += (inA ? texture(tex_from, uvA) : vec4(0.0)) + (inB ? texture(tex_to, uvB) : vec4(0.0)); } f_color = color / float(SAMPLES);
    }
'''
for nome, config in {"limpeza_rapida_direita": {"dir": (1.0, 0.0), "audio": "limpeza_rapida_x.mp3"}, "limpeza_rapida_esquerda": {"dir": (-1.0, 0.0), "audio": "limpeza_rapida_x.mp3"}, "limpeza_rapida_cima": {"dir": (0.0, 1.0), "audio": "limpeza_rapida_y.mp3"}, "limpeza_rapida_baixo": {"dir": (0.0, -1.0), "audio": "limpeza_rapida_y.mp3"}}.items():
    COLECAO_TRANSICOES[nome] = {"audio": config["audio"], "ancora_frames": 4, "fragment": FRAGMENT_LIMPEZA_RAPIDA.replace("{DIR_X}", str(config["dir"][0])).replace("{DIR_Y}", str(config["dir"][1]))}

FRAGMENT_BALANCAR = '''
    #version 330
    uniform sampler2D tex_from; uniform sampler2D tex_to; uniform float progress;
    in vec2 uv; out vec4 f_color;
    const float PI = 3.14159265359; const float DIR_X = {DIR_X};
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    float easeInOutCubic(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }
    vec2 wrap_uv(vec2 p) { return 1.0 - abs(mod(p, 2.0) - 1.0); }
    void main() {
        float ease = easeInOutCubic(progress); vec2 offset = vec2(ease * 2.0 * DIR_X, sin(progress * PI) * 0.25); float angle = sin(progress * PI) * 0.15 * DIR_X; float s = sin(angle); float c = cos(angle); float blur_mask = smoothstep(0.25, 0.45, progress) * (1.0 - smoothstep(0.55, 0.75, progress)); vec2 blur_vec = vec2(DIR_X, 0.2) * blur_mask * 0.15; float noise = hash(uv * 100.0 + progress) - 0.5; vec4 color = vec4(0.0); const int SAMPLES = 32; for (int i = 0; i < SAMPLES; i++) { float f = (float(i) + noise) / float(SAMPLES) - 0.5; vec2 p = uv - 0.5; p = vec2(p.x * c - p.y * s, p.x * s + p.y * c) + 0.5; vec2 sample_uv = p - offset + blur_vec * f; color += mix(texture(tex_from, wrap_uv(sample_uv)), texture(tex_to, wrap_uv(sample_uv)), smoothstep(0.4, 0.6, progress)); } f_color = color / float(SAMPLES);
    }
'''
for nome, dx in {"balancar_direita": 1.0, "balancar_esquerda": -1.0}.items():
    COLECAO_TRANSICOES[nome] = {"audio": "balancar.mp3", "ancora_frames": 10, "fragment": FRAGMENT_BALANCAR.replace(r"{DIR_X}", str(dx))}

def prioridade_camada(camada):
    if camada == 'v3': return 3
    if camada == 'v2': return 2
    return 1

def achatar_camadas(cenas_brutas):
    if not cenas_brutas: return []
    cenas_validas = [c for c in cenas_brutas if c is not None]
    if not cenas_validas: return []

    pontos = set()
    for c in cenas_validas:
        pontos.add(c['inicio'])
        pontos.add(c['fim'])
    pontos_corte = sorted(list(pontos))

    planificadas = []
    cena_atual = None
    inicio_atual = 0.0

    for i in range(len(pontos_corte) - 1):
        t_inicio = pontos_corte[i]; t_fim = pontos_corte[i+1]; meio = (t_inicio + t_fim) / 2.0
        vencedora = None; maior_prio = -1

        for c in cenas_validas:
            if c['inicio'] <= meio <= c['fim']:
                prio = prioridade_camada(c.get('camada', 'v1'))
                if prio > maior_prio: maior_prio = prio; vencedora = c

        if vencedora is None: vencedora = {'id': -1, 'inicio': t_inicio, 'fim': t_fim, 'is_black': True}

        diff = True
        if cena_atual is not None:
            if cena_atual.get('id') == vencedora.get('id') and cena_atual.get('is_black') == vencedora.get('is_black'): diff = False

        if diff:
            if cena_atual is not None:
                nova_cena = cena_atual.copy(); nova_cena['inicio'] = inicio_atual; nova_cena['fim'] = t_inicio
                if nova_cena['fim'] - nova_cena['inicio'] > 0.03: planificadas.append(nova_cena)
            cena_atual = vencedora; inicio_atual = t_inicio

    if cena_atual is not None:
        nova_cena = cena_atual.copy(); nova_cena['inicio'] = inicio_atual; nova_cena['fim'] = pontos_corte[-1]
        if nova_cena['fim'] - nova_cena['inicio'] > 0.03: planificadas.append(nova_cena)

    return planificadas

def get_animacao(cena, idx):
    if cena.get('animacao') and cena.get('animacao') != 'auto': return cena['animacao']
    quadros = cena.get('quadros_foco', [5])
    if len(quadros) >= 5: return 'nenhuma'
    anims = ['zoom_in', 'zoom_out', 'pan']
    return anims[idx % len(anims)]

def get_transicao(cena, idx):
    if cena.get('transicao') and cena.get('transicao') != 'auto': return cena['transicao']
    trans_keys = list(COLECAO_TRANSICOES.keys())
    return trans_keys[idx % len(trans_keys)]

class ModernGLTransitioner:
    def __init__(self, ctx, size, fragment_shader):
        self.ctx = ctx; self.size = size
        self.prog = self.ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=fragment_shader)
        self.vbo = self.ctx.buffer(VERTICES_PADRAO)
        self.vao = self.ctx.vertex_array(self.prog, [(self.vbo, '2f 2f', 'in_vert', 'in_texcoord')])
        self.fbo = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, 3, alignment=1)])
        self.tex_from = self.ctx.texture(self.size, 3, alignment=1); self.tex_to = self.ctx.texture(self.size, 3, alignment=1)

    def render_frame(self, frame_from, frame_to, progress):
        self.tex_from.write(frame_from.tobytes()); self.tex_to.write(frame_to.tobytes())
        self.tex_from.use(0); self.tex_to.use(1)
        self.prog['tex_from'].value = 0; self.prog['tex_to'].value = 1; self.prog['progress'].value = progress
        self.fbo.use(); self.vao.render(moderngl.TRIANGLE_STRIP)
        raw_data = self.fbo.read(components=3, alignment=1)
        return np.frombuffer(raw_data, dtype=np.uint8).reshape((self.size[1], self.size[0], 3))

class GPUImageAnimator:
    def __init__(self, ctx, size):
        self.ctx = ctx; self.size = size
        self.prog = self.ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader='''
                #version 330
                uniform sampler2D tex_image; uniform float scale; uniform vec2 uv_scale; uniform vec2 focus_uv; uniform bool is_black; 
                in vec2 uv; out vec4 f_color;
                void main() {
                    if (is_black) { f_color = vec4(0.0, 0.0, 0.0, 1.0); return; }
                    vec2 st = (uv - vec2(0.5)) * (uv_scale / scale) + focus_uv;
                    if(st.x < 0.0 || st.x > 1.0 || st.y < 0.0 || st.y > 1.0) f_color = vec4(0.0, 0.0, 0.0, 1.0); else f_color = texture(tex_image, st);
                }
            '''
        )
        self.vbo = self.ctx.buffer(VERTICES_PADRAO); self.vao = self.ctx.vertex_array(self.prog, [(self.vbo, '2f 2f', 'in_vert', 'in_texcoord')])
        self.fbo = self.ctx.framebuffer(color_attachments=[self.ctx.texture(size, 3, alignment=1)])

class FundoGPU:
    def __init__(self, ctx, res_render, animador_gpu, cena_raw, is_black=False):
        self.ctx = ctx; self.res_render = res_render; self.animador_gpu = animador_gpu; self.tex = None; self.is_black_scene = is_black
        
        self.anim_start = cena_raw.get('anim_start', 0.0)
        self.anim_end = cena_raw.get('anim_end', 1.0)
        self.anim_easing = cena_raw.get('anim_easing', 'linear')

        if self.is_black_scene:
            self.modo = "nenhuma"; self.start_scale = 1.0; self.end_scale = 1.0; self.start_focus = (0.5, 0.5); self.end_focus = (0.5, 0.5); self.uv_scale = (1.0, 1.0); self.focus_uv = (0.5, 0.5)
            return 

        nome_arquivo = cena_raw.get('arquivo_origem', None)
        caminho_img = None

        if nome_arquivo:
            caminho_img = os.path.join(PASTA_MIDIA, nome_arquivo)
            if not os.path.exists(caminho_img): caminho_img = None 

        if not caminho_img:
            idx_cena = cena_raw.get('id', 0)
            caminho_img = os.path.join(PASTA_UPSCALE, f"cena_{idx_cena:03d}.jpg")
            if not os.path.exists(caminho_img): caminho_img = os.path.join(PASTA_IMAGENS, f"cena_{idx_cena:03d}.jpg")
        
        if not os.path.exists(caminho_img):
            self.is_black_scene = True; return

        self.is_video = caminho_img.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi'))
        self.v_clip = None

        if self.is_video:
            self.v_clip = VideoFileClip(caminho_img)
            w, h = self.v_clip.size
            img_aspect = w / h
            frame0 = self.v_clip.get_frame(0)
            self.tex = self.ctx.texture((w, h), 3, frame0.tobytes(), alignment=1)
        else:
            img_pil = Image.open(caminho_img).convert('RGB')
            img_pil = ImageOps.exif_transpose(img_pil) 
            self.tex = self.ctx.texture(img_pil.size, 3, img_pil.tobytes(), alignment=1)
            img_aspect = img_pil.width / img_pil.height

        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR) 
            
        quadros_foco = cena_raw.get('quadros_foco', [5])
        cx_total, cy_total = 0, 0
        for q in quadros_foco:
            if not isinstance(q, int) or q < 1 or q > 9: q = 5
            row, col = (q - 1) // 3, (q - 1) % 3
            cx_total += (col * (1/3)) + (1/6); cy_total += (row * (1/3)) + (1/6)
            
        raw_focus_u = cx_total / len(quadros_foco); raw_focus_v = cy_total / len(quadros_foco)
        
        screen_aspect = self.res_render[0] / self.res_render[1]
        
        if img_aspect > screen_aspect: self.uv_scale = (screen_aspect / img_aspect, 1.0)
        else: self.uv_scale = (1.0, img_aspect / screen_aspect)

        margem_u = self.uv_scale[0] / 2.0; margem_v = self.uv_scale[1] / 2.0
        safe_focus_u = max(margem_u, min(1.0 - margem_u, raw_focus_u)); safe_focus_v = max(margem_v, min(1.0 - margem_v, raw_focus_v))
        self.focus_uv = (safe_focus_u, safe_focus_v)
        
        self.modo = get_animacao(cena_raw, cena_raw.get('id', 0))
        zoom_padrao = cena_raw.get('zoom_intensity', 0.15)
        
        if self.modo == "nenhuma":
            self.start_scale = 1.0; self.end_scale = 1.0; self.start_focus = self.focus_uv; self.end_focus = self.focus_uv
        elif self.modo == "zoom_in":
            self.start_scale = 1.0; self.end_scale = 1.0 + zoom_padrao; self.start_focus = self.focus_uv; self.end_focus = self.focus_uv
        elif self.modo == "zoom_out":
            self.start_scale = 1.0 + zoom_padrao; self.end_scale = 1.0; self.start_focus = self.focus_uv; self.end_focus = self.focus_uv
        else: 
            self.start_scale = 1.15; self.end_scale = 1.15
            offset = 0.05
            if img_aspect > screen_aspect:
                sx = max(margem_u, min(1.0 - margem_u, self.focus_uv[0] - offset)); ex = max(margem_u, min(1.0 - margem_u, self.focus_uv[0] + offset))
                if (cena_raw.get('id', 0) % 2) == 0: sx, ex = ex, sx
                self.start_focus = (sx, self.focus_uv[1]); self.end_focus = (ex, self.focus_uv[1])
            else:
                sy = max(margem_v, min(1.0 - margem_v, self.focus_uv[1] - offset)); ey = max(margem_v, min(1.0 - margem_v, self.focus_uv[1] + offset))
                if (cena_raw.get('id', 0) % 2) == 0: sy, ey = ey, sy
                self.start_focus = (self.focus_uv[0], sy); self.end_focus = (self.focus_uv[0], ey)

    def get_frame(self, progresso, t_local=0.0):
        if self.is_black_scene:
            self.animador_gpu.fbo.use(); self.animador_gpu.prog['is_black'].value = True; self.animador_gpu.vao.render(moderngl.TRIANGLE_STRIP)
            raw_data = self.animador_gpu.fbo.read(components=3, alignment=1)
            return np.frombuffer(raw_data, dtype=np.uint8).reshape((self.res_render[1], self.res_render[0], 3))

        if getattr(self, 'is_video', False) and self.v_clip:
            try:
                t_safe = min(t_local, self.v_clip.duration - 0.001) if self.v_clip.duration else t_local
                frame = self.v_clip.get_frame(t_safe)
                self.tex.write(frame.tobytes())
            except Exception as e:
                pass

        p = progresso
        if self.anim_start >= self.anim_end:
            p_norm = 1.0 if p >= self.anim_end else 0.0
        else:
            if p <= self.anim_start:
                p_norm = 0.0
            elif p >= self.anim_end:
                p_norm = 1.0
            else:
                p_norm = (p - self.anim_start) / (self.anim_end - self.anim_start)

        if self.anim_easing == 'suave':
            p_eased = 2 * p_norm * p_norm if p_norm < 0.5 else 1 - ((-2 * p_norm + 2) ** 2) / 2
        elif self.anim_easing == 'dinamica':
            c1 = 1.70158
            c3 = c1 + 1
            p_eased = 1 + c3 * ((p_norm - 1) ** 3) + c1 * ((p_norm - 1) ** 2)
        else:
            p_eased = p_norm

        escala = self.start_scale + (self.end_scale - self.start_scale) * p_eased
        cur_u = self.start_focus[0] + (self.end_focus[0] - self.start_focus[0]) * p_eased
        cur_v = self.start_focus[1] + (self.end_focus[1] - self.start_focus[1]) * p_eased
        
        self.tex.use(0)
        self.animador_gpu.fbo.use(); self.animador_gpu.prog['is_black'].value = False; self.animador_gpu.prog['tex_image'].value = 0
        self.animador_gpu.prog['scale'].value = escala; self.animador_gpu.prog['uv_scale'].value = self.uv_scale; self.animador_gpu.prog['focus_uv'].value = (cur_u, cur_v)
        
        self.animador_gpu.vao.render(moderngl.TRIANGLE_STRIP)
        raw_data = self.animador_gpu.fbo.read(components=3, alignment=1)
        return np.frombuffer(raw_data, dtype=np.uint8).reshape((self.res_render[1], self.res_render[0], 3))
        
    def close(self):
        if self.tex: self.tex.release()
        if getattr(self, 'v_clip', None): self.v_clip.close()

# ==========================================
# RENDERIZADOR AVANÇADO
# ==========================================
def renderizar_motor_avancado(projeto, arquivo_saida, fps_render, res_render, task_id, dict_status):
    duracao_total = projeto.get('duracao', 10.0)
    audio_path = projeto.get('audio_mestre')
    volume_locucao = float(projeto.get('volume_locucao', 1.0)) 
    vols_camadas = projeto.get('volumes_camadas', {}) 
    
    cenas_brutas = projeto.get('cenas', [])
    for i, c in enumerate(cenas_brutas):
        if c is not None and 'id' not in c: c['id'] = i
    
    timeline_planificada = achatar_camadas(cenas_brutas)
    
    # 1. Configuração do Áudio
    audio_mestre = AudioFileClip(audio_path)
    mult_a1 = float(vols_camadas.get('a1', 1.0))
    if (volume_locucao * mult_a1) != 1.0:
        audio_mestre = audio_mestre.fx(afx.volumex, volume_locucao * mult_a1)

    try: pico_narra = audio_mestre.max_volume()
    except: pico_narra = 1.0
    
    audios_sfx = []
    pasta_audio_transicoes = os.path.join("efeitos_sonoros", "transicoes")
    
    for i in range(len(timeline_planificada) - 1):
        cenaA = timeline_planificada[i]; cenaB = timeline_planificada[i+1]
        if cenaA.get('is_black') or cenaB.get('is_black'): continue
        
        rawA = cenas_brutas[cenaA['id']]
        transName = get_transicao(rawA, rawA['id'])
        
        if transName != 'nenhuma':
            audio_name = transName
            for d in ['_direita', '_esquerda', '_cima', '_baixo']: audio_name = audio_name.replace(d, '')
            if 'limpeza' in audio_name: audio_name = 'limpeza_rapida_x'
            
            caminho_sfx = os.path.join(pasta_audio_transicoes, audio_name + '.mp3')
            duracao_visual = min(1.0, (cenaA['fim'] - cenaA['inicio']) * 0.5, (cenaB['fim'] - cenaB['inicio']) * 0.5) 
            
            if duracao_visual > 0.1 and os.path.exists(caminho_sfx):
                try:
                    trans_vol = rawA.get('transition_volume', 1.0)
                    mult_v = float(vols_camadas.get(rawA.get('camada', 'v1'), 1.0))
                    
                    clip_sfx = AudioFileClip(caminho_sfx).fx(afx.audio_fadeout, 0.3)
                    p_sfx = clip_sfx.max_volume()
                    if p_sfx == 0: p_sfx = 1.0
                    fator = (1.0 / p_sfx) * (pico_narra * 0.20) * trans_vol * mult_v
                    audios_sfx.append(clip_sfx.fx(afx.volumex, fator).set_start(cenaA['fim'] - duracao_visual))
                except: pass

    # ==========================================
    # PROCESSAMENTO DAS FAIXAS MUSICAIS (DAW MULTITRACK)
    # ==========================================
    faixas_musicais = projeto.get('faixas_musicais', [])
    audios_bgm = []

    for faixa in faixas_musicais:
        if not faixa or 'arquivo' not in faixa: continue
        caminho_arq = faixa['arquivo']
        if not os.path.exists(caminho_arq): continue

        try:
            m_clip = AudioFileClip(caminho_arq)
            dur_bloco = faixa['fim'] - faixa['inicio']

            try:
                pico_bgm = m_clip.max_volume()
                if pico_bgm == 0: pico_bgm = 1.0
            except: pico_bgm = 1.0

            vol_relativo = faixa.get('volume', 0.15)
            mult_a2 = float(vols_camadas.get('a2', 1.0))
            fator_volume = ((pico_narra * vol_relativo) / pico_bgm) * mult_a2

            if m_clip.duration < dur_bloco:
                m_clip = afx.audio_loop(m_clip, duration=dur_bloco)
            else:
                m_clip = m_clip.subclip(0, dur_bloco)

            m_clip = m_clip.fx(afx.volumex, fator_volume)

            fade_in = faixa.get('fade_in', 0)
            if fade_in > 0: m_clip = m_clip.fx(afx.audio_fadein, fade_in)

            fade_out = faixa.get('fade_out', 0)
            if fade_out > 0: m_clip = m_clip.fx(afx.audio_fadeout, fade_out)

            m_clip = m_clip.set_start(faixa['inicio'])
            audios_bgm.append(m_clip)
        except Exception as e:
            print(f"[Aviso] Falha ao processar música {caminho_arq}: {e}")

    # ==========================================
    # EXTRAÇÃO DE ÁUDIO DOS VÍDEOS
    # ==========================================
    audios_videos = []
    for cena in cenas_brutas:
        if not cena or 'arquivo_origem' not in cena: continue
        arq = cena['arquivo_origem']
        if arq.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi')):
            caminho_vid = os.path.join(PASTA_MIDIA, arq)
            if os.path.exists(caminho_vid):
                try:
                    v_audio = AudioFileClip(caminho_vid)
                    mult_v = float(vols_camadas.get(cena.get('camada', 'v1'), 1.0))
                    vol_vid = cena.get('volume_video', 1.0) * mult_v
                    if vol_vid != 1.0: v_audio = v_audio.fx(afx.volumex, vol_vid)
                    
                    duracao_real_cena = cena['fim'] - cena['inicio']
                    if v_audio.duration > duracao_real_cena:
                        v_audio = v_audio.subclip(0, duracao_real_cena)
                        
                    v_audio = v_audio.set_start(cena['inicio'])
                    audios_videos.append(v_audio)
                except: pass

    # ==========================================
    # MISTURADOR E GRAVADOR DO ÁUDIO FINAL
    # ==========================================
    clipes_para_mixar = [audio_mestre] + audios_sfx + audios_bgm + audios_videos
    mix_completo = CompositeAudioClip(clipes_para_mixar)
            
    novo_audio_path = "temp_mix_completo.wav"
    mix_completo.write_audiofile(novo_audio_path, fps=44100, logger=None)
    
    mix_completo.close()
    audio_mestre.close()
    for c in audios_sfx: c.close()
    for c in audios_bgm: c.close()
    for c in audios_videos: c.close()
    audio_path = novo_audio_path

    total_frames = int(duracao_total * fps_render) 
    dict_status[task_id]['total_frames'] = total_frames
    
    # --- CRIAÇÃO DO CONTEXTO OPENGL (BLINDADO) ---
    try:
        if SISTEMA == "Linux":
            # Força o backend EGL para rodar sem servidor X (Monitor) no Colab
            ctx = moderngl.create_standalone_context(require=330, backend='egl')
        else:
            ctx = moderngl.create_standalone_context()
    except Exception as e:
        print(f"[AVISO OpenGL] Falha na criação do contexto primário. Tentando fallback... Detalhe: {e}")
        ctx = moderngl.create_standalone_context()
        
    animador_gpu = GPUImageAnimator(ctx, res_render)

    comando_ffmpeg = [
        CAMINHO_FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{res_render[0]}x{res_render[1]}', '-pix_fmt', 'rgb24', '-r', str(fps_render),
        '-i', '-', '-i', audio_path, '-map', '0:v', '-map', '1:a',
        '-c:v', CODEC_VIDEO, '-preset', 'fast', '-b:v', '15M',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
        '-shortest', arquivo_saida
    ]
    processo = subprocess.Popen(comando_ffmpeg, stdin=subprocess.PIPE)
    
    tempo_inicio = time.time()
    idxPlano_atual = -1
    bg_A = None; bg_B = None; engine_trans = None

    for f in range(total_frames):
        t_global = f / fps_render
        
        idxPlano = None
        for i, b in enumerate(timeline_planificada):
            if t_global >= b['inicio'] and t_global < b['fim']:
                idxPlano = i; break
                
        if idxPlano != idxPlano_atual:
            idxPlano_atual = idxPlano
            if bg_A: bg_A.close()
            if bg_B: bg_B.close()
            bg_A = None; bg_B = None; engine_trans = None
            
            if idxPlano is not None and not timeline_planificada[idxPlano].get('is_black'):
                flatA = timeline_planificada[idxPlano]
                rawA = cenas_brutas[flatA['id']]
                bg_A = FundoGPU(ctx, res_render, animador_gpu, rawA)
                
                tipoTrans = get_transicao(rawA, rawA['id'])
                if idxPlano < len(timeline_planificada) - 1 and tipoTrans != 'nenhuma':
                    flatB = timeline_planificada[idxPlano + 1]
                    if not flatB.get('is_black'):
                        rawB = cenas_brutas[flatB['id']]
                        bg_B = FundoGPU(ctx, res_render, animador_gpu, rawB)
                        frag = COLECAO_TRANSICOES.get(tipoTrans, COLECAO_TRANSICOES['zoom_rotacao'])['fragment']
                        engine_trans = ModernGLTransitioner(ctx, res_render, frag)
        
        if idxPlano is None or timeline_planificada[idxPlano].get('is_black'):
            animador_gpu.fbo.use(); animador_gpu.prog['is_black'].value = True; animador_gpu.vao.render(moderngl.TRIANGLE_STRIP)
            raw_data = animador_gpu.fbo.read(components=3, alignment=1)
            frame_render = np.frombuffer(raw_data, dtype=np.uint8).reshape((res_render[1], res_render[0], 3))
        else:
            flatA = timeline_planificada[idxPlano]
            rawA = cenas_brutas[flatA['id']]
            
            durTransAnterior = 0.0
            if idxPlano > 0:
                flatPrev = timeline_planificada[idxPlano - 1]
                if not flatPrev.get('is_black'):
                    rawPrev = cenas_brutas[flatPrev['id']]
                    if get_transicao(rawPrev, rawPrev['id']) != 'nenhuma':
                        durTransAnterior = min(1.0, (flatPrev['fim'] - flatPrev['inicio'])*0.5, (flatA['fim'] - flatA['inicio'])*0.5)
                        
            duracaoVisualA = (flatA['fim'] - flatA['inicio']) + durTransAnterior
            t_local_A = (t_global - flatA['inicio']) + durTransAnterior
            prog_A = min(t_local_A / duracaoVisualA, 1.0) if duracaoVisualA > 0 else 1.0
            
            inTransition = False
            tipoTrans = get_transicao(rawA, rawA['id'])
            
            if idxPlano < len(timeline_planificada) - 1 and tipoTrans != 'nenhuma':
                flatB = timeline_planificada[idxPlano + 1]
                if not flatB.get('is_black'):
                    duracaoTrans = min(1.0, (flatA['fim'] - flatA['inicio']) * 0.5, (flatB['fim'] - flatB['inicio']) * 0.5)
                    inicioTrans = flatA['fim'] - duracaoTrans
                    if t_global >= inicioTrans and t_global <= flatA['fim']:
                        inTransition = True
                        prog_Trans = (t_global - inicioTrans) / duracaoTrans
                        
                        duracaoVisualB = (flatB['fim'] - flatB['inicio']) + duracaoTrans
                        t_local_B = t_global - inicioTrans
                        prog_B = min(t_local_B / duracaoVisualB, 1.0) if duracaoVisualB > 0 else 1.0
                        
                        frame_render = engine_trans.render_frame(bg_A.get_frame(prog_A, t_local_A), bg_B.get_frame(prog_B, t_local_B), prog_Trans)
            
            if not inTransition:
                frame_render = bg_A.get_frame(prog_A, t_local_A)
                
        processo.stdin.write(frame_render.tobytes())
        
        if f % 5 == 0 or f == total_frames - 1:
            decorrido = time.time() - tempo_inicio
            fps_atual = (f + 1) / decorrido if decorrido > 0 else 0
            porcentagem = int(((f + 1) / total_frames) * 100)
            dict_status[task_id]['frame_atual'] = f + 1
            dict_status[task_id]['progresso'] = porcentagem
            dict_status[task_id]['fps'] = round(fps_atual, 1)

    processo.stdin.close()
    processo.wait()
    
    # Libera os blocos da VRAM para a próxima renderização
    ctx.release()

    if 'temp_mix_completo.wav' in audio_path and os.path.exists(audio_path): os.remove(audio_path)
        
    dict_status[task_id]['estado'] = 'concluido'
    dict_status[task_id]['progresso'] = 100
    nome_arquivo = os.path.basename(arquivo_saida)
    dict_status[task_id]['url_video'] = f"/saida_video/{nome_arquivo}"
    print(f"\n[RENDER] Finalizado com Sucesso! Arquivo salvo em {arquivo_saida}")