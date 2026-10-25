"""Article media discovery and bounded, verified local image storage."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import warnings

from PIL import Image

from .models import digest, normalize_url, utcnow

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 6
MIN_IMAGE_AREA = 400 * 400
MIN_IMAGE_SIDE = 200
FORMATS = {"JPEG":("jpg","image/jpeg"),"PNG":("png","image/png"),"WEBP":("webp","image/webp"),
           "GIF":("gif","image/gif"),"AVIF":("avif","image/avif")}


class ImageFiltered(ValueError):
    pass


def image_url(base, value):
    if not isinstance(value,str) or not value.strip():
        return None
    url = urljoin(base,value.strip())
    try:
        normalize_url(url)  # Validate only: preserve ordering/signatures of CDN query parameters.
    except ValueError:
        return None
    parts = urlsplit(url)
    if parts.path.lower().endswith(".svg"):
        return None
    return urlunsplit((parts.scheme,parts.netloc,parts.path,parts.query,""))


def candidates(tree, source, canonical, ld):
    result, seen = [], set()
    article_id = digest(canonical)
    bases = tree.xpath('//base[@href]/@href')
    base = urljoin(canonical,bases[0]) if bases else canonical
    def add(value, role, origin, alt="", caption=""):
        url = image_url(base,value)
        if not url or url in seen or len(result)>=30:
            return
        seen.add(url)
        result.append({"id":digest(article_id+"\n"+url),"article_id":article_id,"url":url,
                       "role":role,"origin":origin,"alt":alt.strip(),"caption":caption.strip(),
                       "status":"pending","local_path":None})
    def ld_images(value):
        if isinstance(value,list):
            for item in value:
                yield from ld_images(item)
        elif isinstance(value,str):
            yield value
        elif isinstance(value,dict):
            yield value.get("contentUrl") or value.get("url")
    for url in ld_images(ld.get("image",[])):
        add(url,"lead","jsonld")
    for name in ("og:image:secure_url","og:image","twitter:image","twitter:image:src"):
        for url in tree.xpath('//meta[@property=$name or @name=$name]/@content',name=name):
            add(url,"lead",name)
    roots = tree.xpath("//article")
    # A site's body selectors often point to paragraphs; include their direct
    # parent for figure siblings without scanning unrelated global sidebars.
    for selector in source.body_selectors:
        for node in tree.xpath(selector):
            if not isinstance(node,str):
                roots.append(node.getparent() if node.tag in ("p","li") else node)
    for root in roots:
        for node in root.xpath('.//img[not(ancestor::aside or ancestor::nav or ancestor::footer)]'):
            classes = " ".join((parent.get("class","")+" "+parent.get("id","") for parent in [node,*node.iterancestors()]))
            if any(word in classes.casefold() for word in ("avatar","author-photo","related","recommend","social-icon","advert","subscription","newsletter","get-app","whatsapp","person-block","info-block")):
                continue
            srcset = node.get("data-srcset") or node.get("srcset") or ""
            variants = []
            for item in srcset.split(","):
                parts = item.strip().split()
                if parts:
                    try:
                        weight = float(parts[-1][:-1]) if len(parts)>1 else 0
                    except ValueError:
                        weight = 0
                    variants.append((weight,parts[0]))
            url = max(variants,key=lambda pair:pair[0])[1] if variants else None
            url = url or node.get("data-src") or node.get("data-original") or node.get("data-lazy-src") or node.get("src")
            if any(word in (url or "").casefold() for word in ("/themes/","/profiles/custom/","loading.gif","placeholder","game_icon")):
                continue
            links = node.xpath("ancestor::a[1]/@href")
            if links:
                target = image_url(base,links[0])
                if target:
                    path = urlsplit(target).path.lower()
                    if not path.endswith((".jpg",".jpeg",".png",".webp",".avif",".gif")) and normalize_url(target)!=normalize_url(canonical):
                        continue
            figures = node.xpath("ancestor::figure[1]//figcaption//text()")
            add(url,"body","article_img",node.get("alt", "")," ".join(figures))
    return result


def merge_images(images, previous, runtime):
    saved = {x["url"]:x for x in previous}
    result = []
    for candidate in images:
        old = saved.get(candidate["url"])
        if old and old.get("status")=="saved" and old.get("local_path") and (runtime/old["local_path"]).is_file():
            candidate = {**candidate,**old}
            w,h = old.get("width",0),old.get("height",0)
            if min(w,h)<MIN_IMAGE_SIDE or w*h<MIN_IMAGE_AREA:
                candidate.update(status="filtered",local_path=None,error=f"Small image: {w}x{h}; require area >=160000, short side >=200")
        elif old and old.get("status") in ("failed","filtered"):
            candidate = {**candidate,**old}
        result.append(candidate)
    if any(x["role"]=="lead" and x["status"]=="saved" for x in result):
        result = [x for x in result if x["role"]!="lead" or x["status"]=="saved"]
    if sum(x["status"]=="saved" for x in result)>=MAX_IMAGES:
        result = [x for x in result if x["status"]=="saved"][:MAX_IMAGES]
    return result


def persist_image(runtime, article_id, data):
    if not data or len(data)>MAX_IMAGE_BYTES:
        raise ValueError("Empty image or image exceeds 10 MiB")
    with warnings.catch_warnings():
        warnings.simplefilter("error",Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as picture:
            width,height = picture.size
            format_name = picture.format
            if format_name not in FORMATS:
                raise ValueError("Unsupported raster image format")
            if min(width,height)<MIN_IMAGE_SIDE or width*height<MIN_IMAGE_AREA:
                raise ImageFiltered(f"Small image: {width}x{height}; require area >=160000, short side >=200")
            if width*height>40_000_000:
                raise ValueError("Image exceeds 40 megapixels")
            picture.verify()
    extension,mime = FORMATS[format_name]
    sha = hashlib.sha256(data).hexdigest()
    relative = Path("images")/article_id/(sha+"."+extension)
    destination = runtime/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix+".tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)
    return {"local_path":relative.as_posix(),"sha256":sha,"bytes":len(data),"width":width,"height":height,
            "mime_type":mime,"downloaded_at":utcnow(),"status":"saved"}


def download_images(browser, runtime, canonical, title, images, previous=(), stop=None):
    article_id = digest(canonical)
    images = merge_images(images,previous,runtime)
    result = []
    saved_lead = False
    saved_count = 0
    attempts = 0
    for candidate in images:
        if saved_count>=MAX_IMAGES or (candidate["role"]=="lead" and saved_lead):
            continue
        if stop and stop.is_set():
            result.append(candidate)
            continue
        candidate = dict(candidate)
        if candidate.get("status")=="filtered":
            result.append(candidate)
            continue
        if candidate.get("status")!="saved":
            if attempts>=12:
                result.append(candidate)
                continue
            attempts += 1
            try:
                data = browser.image_bytes(candidate["url"],MAX_IMAGE_BYTES)
                candidate.update(persist_image(runtime,article_id,data))
                candidate.pop("error",None)
            except ImageFiltered as exc:
                candidate.update(status="filtered",local_path=None,error=str(exc))
            except Exception as exc:
                candidate.update(status="failed",local_path=None,error=str(exc)[:500])
        if candidate["status"]=="saved":
            saved_count += 1
            saved_lead |= candidate["role"]=="lead"
        result.append(candidate)
    main = next((x["local_path"] for x in result if x["status"]=="saved"),None)
    write_manifest(runtime,canonical,title,result,main)
    return result,main


def write_manifest(runtime,canonical,title,images,main):
    article_id = digest(canonical)
    folder = runtime/"images"/article_id
    folder.mkdir(parents=True,exist_ok=True)
    manifest = {"article_id":article_id,"canonical_url":canonical,"title":title,"main_image_path":main,"images":images}
    temporary = folder/"manifest.json.tmp"
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(folder/"manifest.json")
