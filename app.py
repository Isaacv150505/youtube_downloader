from flask import Flask, render_template, request, send_file, redirect, url_for, Response, jsonify
import yt_dlp
import os
import tempfile
import threading
import time
import uuid
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# Diccionario para rastrear el estado de las descargas
download_status = {}

# Filtro personalizado para formatear tiempo
@app.template_filter('format_duration')
def format_duration(seconds):
    if not seconds:
        return "N/A"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"

# Filtro para formatear tamaño de archivo
@app.template_filter('format_filesize')
def format_filesize(bytes_size):
    if not bytes_size or bytes_size <= 0:
        return "Calculando..."
    
    # Convertir bytes a MB
    mb_size = bytes_size / (1024 * 1024)
    if mb_size < 1:
        kb_size = bytes_size / 1024
        return f"{kb_size:.1f} KB"
    elif mb_size < 1024:
        return f"{mb_size:.1f} MB"
    else:
        gb_size = mb_size / 1024
        return f"{gb_size:.2f} GB"

# Configuración mejorada para yt-dlp con formatos reales disponibles
def get_video_info(url):
    try:
        # Configuración de yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extraer información del video
            info = ydl.extract_info(url, download=False)
            
            # Crear formatos basados en los disponibles realmente
            formats = []
            available_formats = info.get('formats', [])
            
            # Opción 1: Mejor calidad automática (RECOMENDADO)
            formats.append({
                'format_id': 'best',
                'resolution': 'Mejor Calidad',
                'filesize': 0,
                'ext': 'mp4',
                'quality': 2000,
                'description': 'Mejor video y audio disponible (automático)'
            })
            
            # Opción 2: Mejores formatos combinados
            formats.append({
                'format_id': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'resolution': 'HD Combinado',
                'filesize': 0,
                'ext': 'mp4',
                'quality': 1500,
                'description': 'Video HD + mejor audio combinados'
            })
            
            # Buscar formatos específicos disponibles
            video_formats = {}
            for fmt in available_formats:
                if fmt.get('vcodec') != 'none' and fmt.get('height'):
                    height = fmt.get('height')
                    if height and height not in video_formats:
                        video_formats[height] = fmt
            
            # Añadir formatos por resolución encontrados
            common_resolutions = [1080, 720, 480, 360, 240]
            for res in common_resolutions:
                if res in video_formats or any(f.get('height') == res for f in available_formats):
                    formats.append({
                        'format_id': f'best[height<={res}]',
                        'resolution': f'{res}p',
                        'filesize': 0,
                        'ext': 'mp4',
                        'quality': res,
                        'description': f'Video hasta {res}p con audio'
                    })
            
            # Formatos de audio
            formats.append({
                'format_id': 'bestaudio',
                'resolution': 'Solo Audio',
                'filesize': 0,
                'ext': 'm4a',
                'quality': 1,
                'description': 'Solo audio en mejor calidad'
            })
            
            # Audio MP3
            formats.append({
                'format_id': 'bestaudio[ext=m4a]/bestaudio',
                'resolution': 'Audio M4A',
                'filesize': 0,
                'ext': 'm4a',
                'quality': 2,
                'description': 'Audio en formato M4A'
            })
            
            return {
                'title': info.get('title', 'Video sin título'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'formats': formats,
                'error': None
            }
            
    except Exception as e:
        print(f"Error al obtener info del video: {str(e)}")
        return {'error': f'Error al procesar el video: {str(e)}'}

def progress_hook(d, download_id):
    """Hook para rastrear el progreso de descarga"""
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

def download_video_async(url, format_id, output_path, download_id):
    """Descarga el video de forma asíncrona con seguimiento de progreso y audio garantizado"""
    try:
        download_status[download_id] = {'status': 'starting', 'progress': 0}
        
        # Lista de formatos de fallback
        fallback_formats = [
            format_id,  # Formato solicitado
            'best',     # Mejor disponible
            'worst'     # Último recurso
        ]
        
        for attempt, fallback_format in enumerate(fallback_formats):
            try:
                print(f"DEBUG ASYNC: Intento {attempt + 1} con formato: {fallback_format}")
                
                # Configuración mejorada para garantizar audio
                ydl_opts = {
                    'format': fallback_format,
                    'outtmpl': output_path,
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [lambda d: progress_hook(d, download_id)],
                    'merge_output_format': 'mp4',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    'writeinfojson': False,
                    'writesubtitles': False,
                    'writeautomaticsub': False,
                    'embed_subs': False,
                    'ignoreerrors': False,
                    'retries': 3,
                    'fragment_retries': 3,
                    'prefer_ffmpeg': True,
                    'fixup': 'detect_or_warn',
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                print(f"DEBUG ASYNC: ¡Descarga exitosa con formato {fallback_format}!")
                return True
                
            except Exception as attempt_error:
                print(f"DEBUG ASYNC: Error con formato {fallback_format}: {str(attempt_error)}")
                if attempt == len(fallback_formats) - 1:  # Último intento
                    download_status[download_id] = {'status': 'error', 'error': str(attempt_error)}
                    return False
                continue
        
        return False
        
    except Exception as e:
        print(f"Error crítico en descarga asíncrona: {str(e)}")
        download_status[download_id] = {'status': 'error', 'error': str(e)}
        return False

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        
        if not url:
            return render_template('index.html', error='Por favor ingresa una URL válida')
        
        # Validar que sea una URL de YouTube
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return render_template('index.html', error='Por favor ingresa una URL válida de YouTube')
        
        print(f"Procesando URL: {url}")
        video_info = get_video_info(url)
        
        if video_info.get('error'):
            return render_template('index.html', error=video_info['error'])
        
        return render_template('index.html', 
                             video_info=video_info, 
                             original_url=url)
    
    return render_template('index.html')

@app.route('/start_download', methods=['POST'])
def start_download():
    """Inicia la descarga y devuelve un ID para rastrear el progreso"""
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    
    if not url or not format_id:
        return jsonify({'error': 'Datos incompletos'}), 400
    
    # Generar ID único para esta descarga
    download_id = str(uuid.uuid4())
    
    try:
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        
        # Obtener información básica del video
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
        
        # Limpiar título para nombre de archivo
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title[:50] if safe_title else "video"
        
        # Configurar template de salida
        output_template = os.path.join(temp_dir, f"{safe_title}.%(ext)s")
        
        # Iniciar descarga en hilo separado
        download_thread = threading.Thread(
            target=download_video_async,
            args=(url, format_id, output_template, download_id)
        )
        download_thread.daemon = True
        download_thread.start()
        
        return jsonify({
            'download_id': download_id,
            'status': 'started'
        })
        
    except Exception as e:
        print(f"Error al iniciar descarga: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download_progress/<download_id>')
def download_progress(download_id):
    """Devuelve el progreso de una descarga específica"""
    if download_id in download_status:
        return jsonify(download_status[download_id])
    else:
        return jsonify({'error': 'Descarga no encontrada'}), 404

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Descarga el archivo una vez completado"""
    if download_id not in download_status:
        return "Descarga no encontrada", 404
    
    status = download_status[download_id]
    
    if status['status'] != 'finished':
        return "Descarga no completada", 400
    
    file_path = status['filename']
    
    if not os.path.exists(file_path):
        return "Archivo no encontrado", 404
    
    # Obtener nombre del archivo
    filename = os.path.basename(file_path)
    
    # Determinar tipo MIME
    file_ext = filename.split('.')[-1].lower()
    mime_types = {
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        'mkv': 'video/x-matroska',
        'avi': 'video/x-msvideo',
        'mov': 'video/quicktime',
        'm4a': 'audio/mp4',
        'mp3': 'audio/mpeg'
    }
    mime_type = mime_types.get(file_ext, 'application/octet-stream')
    
    # Función para limpiar archivos después del envío
    def remove_temp_files():
        try:
            temp_dir = os.path.dirname(file_path)
            os.remove(file_path)
            os.rmdir(temp_dir)
            # Limpiar del diccionario de estado
            if download_id in download_status:
                del download_status[download_id]
            print(f"Archivos temporales eliminados para {download_id}")
        except Exception as e:
            print(f"Error al eliminar archivos temporales: {e}")
    
    # Programar limpieza después de 60 segundos
    threading.Timer(60.0, remove_temp_files).start()
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=mime_type
    )

# ENDPOINT ORIGINAL MEJORADO para garantizar audio
@app.route('/download', methods=['POST'])
def download():
    """Endpoint original mejorado - CON AUDIO GARANTIZADO"""
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    
    print(f"DEBUG: Iniciando descarga - URL: {url}, Format ID: {format_id}")
    
    if not url or not format_id:
        print("ERROR: Datos incompletos")
        return "Datos incompletos", 400
    
    try:
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        print(f"DEBUG: Directorio temporal creado: {temp_dir}")
        
        # Obtener información básica del video
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
        
        # Limpiar título para nombre de archivo
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title[:50] if safe_title else "video"
        print(f"DEBUG: Título seguro: {safe_title}")
        
        # Configurar descarga con nombre específico
        output_template = os.path.join(temp_dir, f"{safe_title}.%(ext)s")
        print(f"DEBUG: Template de salida: {output_template}")
        
        # CONFIGURACIÓN CRÍTICA: Más flexible y robusta
        ydl_opts = {
            'format': format_id,
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            
            # OPCIONES FLEXIBLES PARA AUDIO
            'merge_output_format': 'mp4',
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }
            ],
            
            # Opciones de compatibilidad y recuperación
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'embed_subs': False,
            'ignoreerrors': False,
            'retries': 3,
            'fragment_retries': 3,
            'extractor_retries': 2,
            
            # Fallbacks automáticos si el formato exacto no está disponible
            'format_sort': ['res', 'ext:mp4:m4a'],
            'prefer_ffmpeg': True,
            'fixup': 'detect_or_warn',
            
            # Si no encuentra el formato exacto, usar el mejor disponible
            'ignoreerrors': False,
        }
        
        print(f"DEBUG: Iniciando descarga con yt-dlp (CON AUDIO)...")
        
        # MANEJO DE ERRORES CON FALLBACKS
        success = False
        fallback_formats = [
            format_id,  # Formato solicitado originalmente
            'best',     # Mejor disponible
            'worst',    # Peor disponible (como último recurso)
        ]
        
        for attempt, fallback_format in enumerate(fallback_formats):
            try:
                print(f"DEBUG: Intento {attempt + 1} con formato: {fallback_format}")
                
                # Actualizar formato en opciones
                ydl_opts['format'] = fallback_format
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                success = True
                print(f"DEBUG: ¡Descarga exitosa con formato {fallback_format}!")
                break
                
            except Exception as attempt_error:
                print(f"DEBUG: Error con formato {fallback_format}: {str(attempt_error)}")
                if attempt == len(fallback_formats) - 1:  # Último intento
                    raise attempt_error
                continue
        
        if not success:
            raise Exception("No se pudo descargar con ningún formato disponible")
        
        print(f"DEBUG: Descarga completada, buscando archivos...")
        
        # Buscar archivos en el directorio temporal
        all_files = os.listdir(temp_dir)
        print(f"DEBUG: Archivos encontrados: {all_files}")
        
        if not all_files:
            print("ERROR: No se encontraron archivos descargados")
            return "Error: No se pudo descargar el archivo", 500
        
        # Buscar el archivo MP4 (debería ser el procesado final)
        mp4_files = [f for f in all_files if f.endswith('.mp4')]
        if mp4_files:
            downloaded_file = mp4_files[0]  # Usar el MP4 procesado
        else:
            downloaded_file = all_files[0]  # Fallback al primer archivo
        
        file_path = os.path.join(temp_dir, downloaded_file)
        
        print(f"DEBUG: Enviando archivo: {file_path}")
        
        # Verificar que el archivo existe y tiene contenido
        if not os.path.exists(file_path):
            print("ERROR: El archivo no existe")
            return "Error: El archivo descargado no existe", 500
        
        file_size = os.path.getsize(file_path)
        print(f"DEBUG: Tamaño del archivo: {file_size} bytes")
        
        if file_size == 0:
            print("ERROR: El archivo está vacío")
            return "Error: El archivo descargado está vacío", 500
        
        # ESPERAR para asegurar que el archivo esté completamente procesado
        time.sleep(2)
        
        # Determinar el tipo MIME correcto
        file_ext = downloaded_file.split('.')[-1].lower()
        mime_types = {
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mkv': 'video/x-matroska',
            'avi': 'video/x-msvideo',
            'mov': 'video/quicktime',
            'm4a': 'audio/mp4',
            'mp3': 'audio/mpeg'
        }
        mime_type = mime_types.get(file_ext, 'application/octet-stream')
        
        print(f"DEBUG: Tipo MIME: {mime_type}")
        
        # Función para limpiar archivos después del envío
        def remove_temp_files():
            try:
                time.sleep(10)  # Esperar más tiempo antes de limpiar
                # Eliminar todos los archivos del directorio temporal
                for file in os.listdir(temp_dir):
                    file_path_temp = os.path.join(temp_dir, file)
                    if os.path.exists(file_path_temp):
                        os.remove(file_path_temp)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                print("DEBUG: Archivos temporales eliminados")
            except Exception as e:
                print(f"DEBUG: Error al eliminar archivos temporales: {e}")
        
        # Programar limpieza después de 60 segundos
        threading.Timer(60.0, remove_temp_files).start()
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=downloaded_file,
            mimetype=mime_type
        )
        
    except Exception as e:
        print(f"ERROR CRÍTICO en descarga: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error al descargar: {str(e)}", 500

@app.route('/check_status')
def check_status():
    """Endpoint para verificar el estado del servidor"""
    return jsonify({'status': 'ok', 'message': 'Servidor funcionando correctamente'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)