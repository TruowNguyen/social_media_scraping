"""Bounded local image OCR. Captions and publication timestamps are never replaced."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import hashlib
import os
import shutil
import threading
from urllib.parse import urlsplit
from src.acquisition.models import utcnow

ROOT = Path(__file__).resolve().parents[2]
CONFIG_VERSION = 'tesseract-image-v1-psm6-vie-eng'
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
LOCK = threading.Lock()


def engine_path():
    return os.environ.get('TESSERACT_CMD') or shutil.which('tesseract') or str(ROOT / '.venv/tesseract/tesseract.exe')


@lru_cache(maxsize=4)
def _probe(command, data_dir):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = command
    config = '--tessdata-dir "' + data_dir + '"' if data_dir else ''
    try:
        version = str(pytesseract.get_tesseract_version())
        languages = pytesseract.get_languages(config=config)
        if not {'vie', 'eng'} <= set(languages):
            return {'status':'UNAVAILABLE','error_code':'LANGUAGE_DATA_MISSING','languages':languages}
        actual_dir = Path(data_dir) if data_dir else Path(command).parent / 'tessdata'
        hashes = {lang:hashlib.sha256((actual_dir / (lang+'.traineddata')).read_bytes()).hexdigest() for lang in ('vie','eng')}
        return {'status':'AVAILABLE','engine_version':version,'traineddata_version':hashes,'languages':languages}
    except Exception:
        return {'status':'UNAVAILABLE','error_code':'OCR_ENGINE_UNAVAILABLE'}


def probe():
    try:
        with LOCK:
            return _probe(engine_path(), os.environ.get('TESSDATA_PREFIX',''))
    except ImportError:
        return {'status':'UNAVAILABLE','error_code':'OCR_PYTHON_DEPENDENCY_MISSING'}


def allowed_image_url(url):
    p = urlsplit(url)
    return p.scheme == 'https' and not p.username and not p.password and p.port in (None,443) and bool(p.hostname) and p.hostname.endswith('.fbcdn.net')


def fetch_image(page, url, deadline):
    """Transfer session cookies only in memory. Validate each redirect; stream with a cap."""
    import requests
    import time
    deadline.check()
    start = time.monotonic()
    with requests.Session() as session:
        for _ in range(4):
            if not allowed_image_url(url):
                raise ValueError('IMAGE_HOST_NOT_ALLOWED')
            cookies={c['name']:c['value'] for c in page.context.cookies([url])}
            timeout=max(.1,min(15-(time.monotonic()-start),deadline.remaining()))
            if timeout<=.1:raise TimeoutError('IMAGE_DOWNLOAD_TIMEOUT')
            with session.get(url,cookies=cookies,headers={'User-Agent':page.evaluate('navigator.userAgent')},
                             stream=True,timeout=timeout,allow_redirects=False) as response:
                if response.status_code in {301,302,303,307,308}:
                    from urllib.parse import urljoin
                    url=urljoin(url,response.headers.get('Location',''));continue
                if response.status_code in {401,403,404,410}:raise ValueError('IMAGE_URL_UNAVAILABLE')
                if response.status_code!=200:raise ValueError('IMAGE_DOWNLOAD_FAILED')
                if not response.headers.get('Content-Type','').lower().startswith('image/'):
                    raise ValueError('IMAGE_CONTENT_TYPE_INVALID')
                if int(response.headers.get('Content-Length','0'))>MAX_BYTES:raise ValueError('IMAGE_TOO_LARGE')
                data=bytearray()
                for chunk in response.iter_content(65536):
                    deadline.check()
                    if time.monotonic()-start>15:raise TimeoutError('IMAGE_DOWNLOAD_TIMEOUT')
                    data.extend(chunk)
                    if len(data)>MAX_BYTES:raise ValueError('IMAGE_TOO_LARGE')
                return bytes(data)
    raise ValueError('IMAGE_REDIRECT_LIMIT')


def recognize(data, timeout=20):
    result={'type':'ocr','schema_version':'image-ocr-v1','status':'FAILED','text':None,
            'quality_status':'UNKNOWN','language':'vie+eng','config_version':CONFIG_VERSION,
            'processed_at':utcnow(),'words':[],'image_sha256':hashlib.sha256(data).hexdigest()}
    health=probe();result.update({k:v for k,v in health.items() if k not in {'status','languages'}})
    if health['status']!='AVAILABLE':return dict(result,status='UNAVAILABLE')
    if len(data)>MAX_BYTES:return dict(result,error_code='IMAGE_TOO_LARGE')
    from PIL import Image,ImageOps,UnidentifiedImageError
    import pytesseract
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width*source.height>MAX_PIXELS:return dict(result,error_code='IMAGE_PIXEL_LIMIT')
            source.verify()
        with Image.open(BytesIO(data)) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
            result.update(width=image.width,height=image.height)
            data_dir=os.environ.get('TESSDATA_PREFIX','')
            config='--psm 6'+(' --tessdata-dir "'+data_dir+'"' if data_dir else '')
            with LOCK:
                pytesseract.pytesseract.tesseract_cmd=engine_path()
                rows=pytesseract.image_to_data(image,lang='vie+eng',config=config,
                                              output_type=pytesseract.Output.DICT,timeout=max(.1,timeout))
            lines={}
            for i,text in enumerate(rows['text']):
                if not text.strip():continue
                confidence=float(rows['conf'][i]);confidence=confidence if confidence>=0 else None
                result['words'].append(dict(text=text,x=rows['left'][i],y=rows['top'][i],w=rows['width'][i],h=rows['height'][i],confidence=confidence))
                key=tuple(rows[k][i] for k in ('page_num','block_num','par_num','line_num'))
                lines.setdefault(key,[]).append(text)
            result['text']='\n'.join(' '.join(line) for line in lines.values()) or None
            confidences=[w['confidence'] for w in result['words'] if w['confidence'] is not None]
            mean=sum(confidences)/len(confidences) if confidences else None
            result.update(status='AVAILABLE' if result['text'] else 'EMPTY',mean_word_confidence=mean,
                          quality_status='ACCEPTABLE' if mean is not None and mean>=70 and min(image.size)>=200 else 'NEEDS_REVIEW')
            return result
    except (UnidentifiedImageError,Image.DecompressionBombError,OSError,ValueError):
        return dict(result,error_code='IMAGE_DECODE_FAILED')
    except RuntimeError:
        return dict(result,error_code='OCR_TIMEOUT')
    except Exception:
        return dict(result,error_code='OCR_FAILED')
