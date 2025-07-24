from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import tempfile
import threading
import time
import uuid
import random
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# Configuración para hosting
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB máximo

# Diccionario para rastrear el estado de las descargas
download_status = {}

# Lista de User Agents para evitar detección
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def cleanup_old_files():
    """Limpia archivos temporales antiguos cada hora"""
    while True:
        try:
            temp_base = tempfile.gettempdir()
            current_time = time.time()
            
            for filename in os.listdir(temp_base):
                if filename.startswith('tmp'):
                    file_path = os.path.join(temp_base, filename)
                    try:
                        if os.path.isfile(file_path):
                            file_age = current_time - os.path.getctime(file_path)
                            if file_age > 3600:  # 1 hora
                                os.remove(file_path)
                                print(f"Archivo temporal eliminado: {filename}")
                    except:
                        pass
        except:
            pass
        
        time.sleep(3600)

# Iniciar limpieza en hilo de fondo
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

# Filtros personalizados
@app.template_filter('format_duration')
def format_duration(seconds):
    if not seconds:
        return "N/A"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"

@app.template_filter('format_filesize')
def format_filesize(bytes_size):
    if not bytes_size or bytes_size <= 0:
        return "Calculando..."
    
    mb_size = bytes_size / (1024 * 1024)
    if mb_size < 1:
        kb_size = bytes_size / 1024
        return f"{kb_size:.1f} KB"
    elif mb_size < 1024:
        return f"{mb_size:.1f} MB"
    else:
        gb_size = mb_size / 1024
        return f"{gb_size:.2f} GB"

def get_video_info(url):
    """Obtener información del video con configuración anti-bot"""
    try:
        # Configuración anti-bot mejorada
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            
            # CONFIGURACIÓN ANTI-BOT
            'http_headers': {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip,deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Opciones adicionales para evitar detección
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],  # Evitar formatos problemáticos
                    'player_client': ['android', 'web'],  # Usar cliente móvil
                }
            },
            
            # Simular comportamiento humano
            'sleep_interval': 1,
            'max_sleep_interval': 3,
            'sleep_interval_requests': 1,
            
            # Reducir detección
            'no_check_certificate': True,
            'prefer_insecure': False,
        }
        
        # Añadir delay aleatorio para parecer humano
        time.sleep(random.uniform(0.5, 2.0))
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            
            # Formatos optimizados para hosting con menor detección
            formats.append({
                'format_id': 'best[height<=720][filesize<50M]/best[height<=720]',
                'resolution': 'HD 720p (Recomendado)',
                'filesize': 0,
                'ext': 'mp4',
                'quality': 2000,
                'description': '🏆 Video HD + Audio (máx. 50MB)'
            })
            
            formats.append({
                'format_id': 'best[height<=480][filesize<25M]/best[height<=480]',
                'resolution': 'SD 480p (Rápido)',
                'filesize': 0,
                'ext': 'mp4',
                'quality': 480,
                'description': '⚡ Descarga rápida (máx. 25MB)'
            })
            
            formats.append({
                'format_id': 'best[height<=360][filesize<15M]/best[height<=360]',
                'resolution': '360p (Liviano)',
                'filesize': 0,
                'ext': 'mp4',
                'quality': 360,
                'description': '📱 Óptimo para móviles (máx. 15MB)'
            })
            
            formats.append({
                'format_id': 'bestaudio[filesize<10M]/bestaudio',
                'resolution': 'Solo Audio',
                'filesize': 0,
                'ext': 'm4a',
                'quality': 1,
                'description': '🎵 Solo audio MP3 (máx. 10MB)'
            })
            
            return {
                'title': info.get('title', 'Video sin título'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': formats,
                'error': None
            }
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error completo: {error_msg}")
        
        # Mensajes de error más amigables
        if "Sign in to confirm" in error_msg or "not a bot" in error_msg:
            return {'error': 'YouTube está bloqueando las descargas temporalmente. Por favor intenta con otro video o espera unos minutos.'}
        elif "Video unavailable" in error_msg:
            return {'error': 'Este video no está disponible. Puede ser privado, estar restringido por región o haber sido eliminado.'}
        elif "Private video" in error_msg:
            return {'error': 'Este video es privado y no se puede descargar.'}
        elif "This live event" in error_msg:
            return {'error': 'No se pueden descargar transmisiones en vivo.'}
        else:
            return {'error': f'Error al procesar el video: {error_msg}'}

def progress_hook(d, download_id):
    """Hook para rastrear progreso"""
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
        
        if total > 0:
            percentage = (downloaded / total) * 100
            download_status[download_id] = {
                'status': 'downloading',
                'progress': percentage,
                'downloaded': downloaded,
                'total': total
            }
    elif d['status'] == 'finished':
        download_status[download_id] = {
            'status': 'finished',
            'progress': 100,
            'filename': d['filename']
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    url = request.form.get('url', '').strip()
    
    if not url:
        return render_template('index.html', error='Por favor ingresa una URL válida')
    
    if 'youtube.com' not in url and 'youtu.be' not in url:
        return render_template('index.html', error='Solo URLs de YouTube son compatibles')
    
    # Añadir delay para evitar spam
    time.sleep(random.uniform(1.0, 2.0))
    
    video_info = get_video_info(url)
    
    if video_info.get('error'):
        return render_template('index.html', error=video_info['error'])
    
    return render_template('index.html', video_info=video_info, original_url=url)

@app.route('/download', methods=['POST'])
def download_video():
    """Descarga optimizada para hosting con anti-bot"""
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    
    if not url or not format_id:
        return jsonify({'error': 'Datos incompletos'}), 400
    
    try:
        # Delay aleatorio anti-bot
        time.sleep(random.uniform(1.0, 3.0))
        
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        
        # Obtener título con configuración anti-bot
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 20,
            'http_headers': {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
        
        # Título seguro
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:25] if safe_title else "video"
        
        output_template = os.path.join(temp_dir, f"{safe_title}.%(ext)s")
        
        # Configuración de descarga anti-bot
        fallback_formats = [
            format_id,
            'best[filesize<30M]',
            'worst[filesize<10M]',
            'bestaudio'
        ]
        
        success = False
        for attempt, fallback_format in enumerate(fallback_formats):
            try:
                print(f"Intento {attempt + 1}: {fallback_format}")
                
                # Delay entre intentos
                if attempt > 0:
                    time.sleep(random.uniform(2.0, 4.0))
                
                ydl_opts = {
                    'format': fallback_format,
                    'outtmpl': output_template,
                    'quiet': False,
                    'no_warnings': False,
                    'socket_timeout': 45,
                    
                    # Configuración anti-bot crítica
                    'http_headers': {
                        'User-Agent': random.choice(USER_AGENTS),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-us,en;q=0.5',
                        'Accept-Encoding': 'gzip,deflate',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    
                    'extractor_args': {
                        'youtube': {
                            'skip': ['hls'],
                            'player_client': ['android', 'web'],
                        }
                    },
                    
                    # Procesamiento
                    'merge_output_format': 'mp4',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    
                    # Configuración conservadora
                    'writeinfojson': False,
                    'writesubtitles': False,
                    'writeautomaticsub': False,
                    'embed_subs': False,
                    'retries': 2,
                    'fragment_retries': 2,
                    'prefer_ffmpeg': True,
                    'fixup': 'detect_or_warn',
                    
                    # Simular comportamiento humano
                    'sleep_interval': 1,
                    'max_sleep_interval': 2,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                success = True
                print(f"✅ Descarga exitosa con formato: {fallback_format}")
                break
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Error con formato {fallback_format}: {error_msg}")
                
                # Si es error de bot, esperar más tiempo
                if "Sign in to confirm" in error_msg or "not a bot" in error_msg:
                    if attempt < len(fallback_formats) - 1:
                        print("⏰ Esperando para evitar detección...")
                        time.sleep(random.uniform(5.0, 10.0))
                
                if attempt == len(fallback_formats) - 1:
                    raise e
                continue
        
        if not success:
            return jsonify({'error': 'YouTube está bloqueando las descargas. Intenta más tarde.'}), 500
        
        # Encontrar archivo descargado
        files = os.listdir(temp_dir)
        if not files:
            return jsonify({'error': 'No se encontró el archivo descargado'}), 500
        
        # Buscar archivo MP4 o el primero disponible
        downloaded_file = None
        for file in files:
            if file.endswith('.mp4'):
                downloaded_file = file
                break
        
        if not downloaded_file:
            downloaded_file = files[0]
        
        file_path = os.path.join(temp_dir, downloaded_file)
        
        # Verificar tamaño
        file_size = os.path.getsize(file_path)
        if file_size > 100 * 1024 * 1024:  # 100MB
            os.remove(file_path)
            os.rmdir(temp_dir)
            return jsonify({'error': 'Archivo demasiado grande para hosting gratuito (máx. 100MB)'}), 400
        
        if file_size == 0:
            os.remove(file_path)
            os.rmdir(temp_dir)
            return jsonify({'error': 'El archivo descargado está vacío'}), 500
        
        # Determinar tipo MIME
        file_ext = downloaded_file.split('.')[-1].lower()
        mime_types = {
            'mp4': 'video/mp4',
            'm4a': 'audio/mp4',
            'webm': 'video/webm',
            'mp3': 'audio/mpeg'
        }
        mime_type = mime_types.get(file_ext, 'application/octet-stream')
        
        # Programar limpieza
        def cleanup():
            time.sleep(300)  # 5 minutos
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                print(f"🧹 Limpieza completada: {downloaded_file}")
            except:
                pass
        
        threading.Timer(0, cleanup).start()
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=downloaded_file,
            mimetype=mime_type
        )
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error crítico: {error_msg}")
        
        # Limpiar archivos en caso de error
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                os.rmdir(temp_dir)
        except:
            pass
        
        if "Sign in to confirm" in error_msg or "not a bot" in error_msg:
            return jsonify({'error': 'YouTube detectó actividad de bot. Espera unos minutos e intenta nuevamente.'}), 429
        else:
            return jsonify({'error': f'Error al descargar: {error_msg}'}), 500

@app.route('/health')
def health_check():
    """Health check para el hosting"""
    return jsonify({'status': 'ok', 'message': 'Servicio activo'})

# Configuración para hosting
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
