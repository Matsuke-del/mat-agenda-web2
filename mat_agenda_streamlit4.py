"""
MAT AGENDA - version Streamlit (PocketBase backend)
====================================================================
- Backend PocketBase (au lieu de Supabase)
- Ecran de login au demarrage (mot de passe simple)
- Authentification automatique a PocketBase
- Reecriture des URLs d'images locales 127.0.0.1 -> URL publique
- Compression auto des images a l'upload
- Image de fond personnalisee (Mat_agenda_logo.png a la racine)
- Tout le reste comme avant : calendrier, liste, stats, plan, taches
"""

import base64
import io
import json
from datetime import datetime, time, date
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps
from streamlit_calendar import calendar
from streamlit_image_coordinates import streamlit_image_coordinates

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(page_title="MAT Agenda", layout="wide", page_icon="🧠")

# ---- Secrets (Streamlit Cloud > Settings > Secrets) ----
# secrets.toml :
#   POCKETBASE_URL           = "https://xxx.trycloudflare.com"
#   POCKETBASE_USER_EMAIL    = "app@matagenda.local"
#   POCKETBASE_USER_PASSWORD = "..."
#   APP_PASSWORD             = "matagenda2026"
#   PUSHOVER_TOKEN           = "..."   (optionnel)
#   PUSHOVER_USER            = "..."   (optionnel)
try:
    POCKETBASE_URL           = st.secrets["POCKETBASE_URL"].rstrip("/")
    POCKETBASE_USER_EMAIL    = st.secrets["POCKETBASE_USER_EMAIL"]
    POCKETBASE_USER_PASSWORD = st.secrets["POCKETBASE_USER_PASSWORD"]
    APP_PASSWORD             = st.secrets["APP_PASSWORD"]
    PUSHOVER_TOKEN           = "a6vqbmhhjyzu19ay371qxhmmwuwnpp"
    PUSHOVER_USER            = "uykkgtvss4kmbyuscgce5xqgdb5ufy"
except (KeyError, FileNotFoundError):
    st.error(
        "⚠️ Configuration manquante. Ajoute dans Streamlit Cloud > Settings > Secrets :\n\n"
        "```toml\n"
        'POCKETBASE_URL = "https://xxx.trycloudflare.com"\n'
        'POCKETBASE_USER_EMAIL = "app@matagenda.local"\n'
        'POCKETBASE_USER_PASSWORD = "..."\n'
        'APP_PASSWORD = "matagenda2026"\n'
        "```"
    )
    st.stop()

APP_URL = "https://mat-agenda-web2-mngwrfjcalzf3kbpdvd99n.streamlit.app"

TECHNICIENS = ["MAT", "Sébastien"]
COULEUR_TECH = {"MAT": "#00ff9c", "Sébastien": "#00ffee"}

# Compression images
COMPRESS_MAX_DIM = 1600
COMPRESS_QUALITY = 85

# =========================================================
# STYLE (avec image de fond, applique avant le login)
# =========================================================

@st.cache_data
def _get_bg_base64(path: str) -> str:
    """Encode l'image de fond en base64 (cache pour eviter de recharger a chaque rerun)."""
    try:
        return base64.b64encode(Path(path).read_bytes()).decode()
    except FileNotFoundError:
        return ""

_bg_b64 = _get_bg_base64("Mat_agenda_logo.png")
_bg_css = (
    f'background-image: linear-gradient(rgba(11, 15, 20, 0.30), rgba(11, 15, 20, 0.40)), '
    f'url("data:image/png;base64,{_bg_b64}");'
    if _bg_b64 else "background: #0b0f14;"
)

st.markdown(f"""
<style>
.stApp {{
    {_bg_css}
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
    color: #e5e7eb;
}}

/* Sidebar avec un fond legerement plus opaque pour la lisibilite */
[data-testid="stSidebar"] {{
    background: rgba(11, 15, 20, 0.92);
    backdrop-filter: blur(6px);
    border-right: 1px solid rgba(239, 68, 68, 0.25);
}}

h1, h2, h3 {{
    color: #00ffee;
    text-shadow: 0 2px 12px rgba(0, 0, 0, 0.6);
}}

.stButton>button {{
    background: rgba(17, 24, 39, 0.85);
    color: #00ff9c;
    border: 1px solid #00ff9c;
    border-radius: 8px;
    backdrop-filter: blur(4px);
}}
.stButton>button:hover {{
    background: #00ff9c;
    color: black;
}}

[data-testid="stMetricValue"] {{ color: #00ff9c; }}

.activity-card {{
    background: rgba(17, 24, 39, 0.88);
    border-left: 4px solid #00ff9c;
    padding: 12px;
    margin: 8px 0;
    border-radius: 8px;
    backdrop-filter: blur(4px);
}}

/* Conteneurs d'expanders et formulaires plus lisibles sur l'image */
[data-testid="stExpander"], [data-testid="stForm"] {{
    background: rgba(17, 24, 39, 0.75);
    border-radius: 8px;
    backdrop-filter: blur(4px);
}}

/* Calendrier : fond legerement opaque pour qu'il reste lisible */
.fc {{
    background: rgba(11, 15, 20, 0.85);
    border-radius: 8px;
    padding: 8px;
    backdrop-filter: blur(4px);
}}
</style>
""", unsafe_allow_html=True)

# =========================================================
# ECRAN DE LOGIN
# =========================================================

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False

if not st.session_state.auth_ok:
    st.title("🔒 MAT AGENDA — Connexion")
    st.write("Entre le mot de passe pour accéder à l'application.")

    with st.form("login_form"):
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Connexion", type="primary")
        if submit:
            if password == APP_PASSWORD:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
    st.stop()

# =========================================================
# CLIENT POCKETBASE
# =========================================================

class PocketBaseClient:
    """Client minimaliste pour PocketBase, equivalent supabase-py basique."""

    def __init__(self, base_url, email, password):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.token = None
        self.user_id = None

    def authenticate(self):
        """Login via le compte 'app' (collection users)."""
        r = requests.post(
            f"{self.base_url}/api/collections/users/auth-with-password",
            json={"identity": self.email, "password": self.password},
            timeout=15
        )
        if r.status_code != 200:
            raise Exception(
                f"Echec authentification PocketBase ({r.status_code}) : {r.text[:200]}"
            )
        data = r.json()
        self.token = data["token"]
        self.user_id = data["record"]["id"]
        return self.token

    def _headers(self, json_content=False):
        h = {}
        if self.token:
            h["Authorization"] = self.token
        if json_content:
            h["Content-Type"] = "application/json"
        return h

    def list_records(self, collection, page=1, per_page=200, sort=None, filter_=None):
        params = {"page": page, "perPage": per_page}
        if sort:
            params["sort"] = sort
        if filter_:
            params["filter"] = filter_
        r = requests.get(
            f"{self.base_url}/api/collections/{collection}/records",
            params=params,
            headers=self._headers(),
            timeout=30
        )
        if r.status_code != 200:
            raise Exception(f"list {collection} : {r.status_code} - {r.text[:200]}")
        return r.json()

    def list_all(self, collection, sort=None, filter_=None):
        """Liste toutes les pages d'une collection."""
        all_items = []
        page = 1
        while True:
            data = self.list_records(collection, page=page, per_page=200,
                                      sort=sort, filter_=filter_)
            all_items.extend(data.get("items", []))
            if page >= data.get("totalPages", 1):
                break
            page += 1
        return all_items

    def create_record(self, collection, payload, files=None):
        if files:
            r = requests.post(
                f"{self.base_url}/api/collections/{collection}/records",
                data=payload, files=files,
                headers=self._headers(), timeout=60
            )
        else:
            r = requests.post(
                f"{self.base_url}/api/collections/{collection}/records",
                json=payload,
                headers=self._headers(json_content=True), timeout=30
            )
        if r.status_code not in (200, 201):
            raise Exception(f"create {collection} : {r.status_code} - {r.text[:300]}")
        return r.json()

    def update_record(self, collection, record_id, payload, files=None):
        if files:
            r = requests.patch(
                f"{self.base_url}/api/collections/{collection}/records/{record_id}",
                data=payload, files=files,
                headers=self._headers(), timeout=60
            )
        else:
            r = requests.patch(
                f"{self.base_url}/api/collections/{collection}/records/{record_id}",
                json=payload,
                headers=self._headers(json_content=True), timeout=30
            )
        if r.status_code != 200:
            raise Exception(f"update {collection}/{record_id} : {r.status_code} - {r.text[:300]}")
        return r.json()

    def delete_record(self, collection, record_id):
        r = requests.delete(
            f"{self.base_url}/api/collections/{collection}/records/{record_id}",
            headers=self._headers(), timeout=30
        )
        if r.status_code not in (200, 204):
            raise Exception(f"delete {collection}/{record_id} : {r.status_code}")
        return True


@st.cache_resource
def get_pb():
    """Client PocketBase mis en cache pour toute la session."""
    pb = PocketBaseClient(POCKETBASE_URL, POCKETBASE_USER_EMAIL, POCKETBASE_USER_PASSWORD)
    pb.authenticate()
    return pb

try:
    pb = get_pb()
except Exception as e:
    st.error(f"❌ Impossible de se connecter à PocketBase :\n\n{e}")
    st.info(
        "Vérifie que :\n"
        "- PocketBase tourne sur ton PC\n"
        "- Cloudflare Tunnel est actif\n"
        "- L'URL POCKETBASE_URL dans les secrets est à jour\n"
        "- Le compte 'app@matagenda.local' existe bien"
    )
    if st.button("🔓 Se déconnecter (Streamlit)"):
        st.session_state.auth_ok = False
        st.rerun()
    st.stop()

# =========================================================
# HELPERS
# =========================================================

def format_date_fr(date_str):
    try:
        d = datetime.strptime(str(date_str), "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(date_str)

def calc_heures(row):
    try:
        d = datetime.strptime(row["debut"], "%H:%M:%S")
        f = datetime.strptime(row["fin"],   "%H:%M:%S")
        return (f - d).seconds / 3600
    except Exception:
        return 0

def send_push(desc, date_str, debut, fin, tech):
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        return
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user":  PUSHOVER_USER,
                "title": "📅 Nouvelle activité",
                "message": f"{desc}\n📆 {date_str}\n⏰ {debut} → {fin}\n👷 {tech}",
                "url": APP_URL,
                "url_title": "📂 Ouvrir MAT Agenda"
            },
            timeout=5
        )
    except Exception:
        pass

def reecrire_url_image(url):
    """Si l'URL pointe vers 127.0.0.1:8090 (PocketBase local),
    la remplace par l'URL publique POCKETBASE_URL."""
    if not isinstance(url, str):
        return url
    if "127.0.0.1:8090" in url:
        return url.replace("http://127.0.0.1:8090", POCKETBASE_URL)
    if "localhost:8090" in url:
        return url.replace("http://localhost:8090", POCKETBASE_URL)
    return url

def parse_images(raw):
    """Retourne toujours une liste d'URL d'images, avec reecriture localhost."""
    if not raw:
        return []
    if isinstance(raw, list):
        urls = [x for x in raw if isinstance(x, str)]
    else:
        try:
            imgs = json.loads(raw)
            if isinstance(imgs, list):
                urls = [x for x in imgs if isinstance(x, str)]
            elif isinstance(imgs, str):
                urls = [imgs]
            else:
                urls = []
        except Exception:
            if isinstance(raw, str) and raw.startswith("http"):
                urls = [raw]
            else:
                urls = []
    return [reecrire_url_image(u) for u in urls]

# =========================================================
# COMPRESSION D'IMAGES
# =========================================================

def compresser_bytes(content_bytes,
                     max_dim=COMPRESS_MAX_DIM,
                     quality=COMPRESS_QUALITY):
    img = Image.open(io.BytesIO(content_bytes))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()

def upload_images_pocketbase(record_id, files):
    """Uploade des fichiers (UploadedFile Streamlit) dans le champ 'images'
    du record PocketBase. Retourne les noms de fichiers stockes."""
    if not files:
        return []

    multipart = []
    for f in files:
        try:
            content_origine = f.getvalue()
            taille_o = len(content_origine)
            content = compresser_bytes(content_origine)
            taille_n = len(content)

            base = f.name.rsplit(".", 1)[0]
            filename = f"{base}.jpg"
            multipart.append(("images", (filename, content, "image/jpeg")))

            ratio = (1 - taille_n / taille_o) * 100 if taille_o else 0
            st.toast(
                f"📦 {f.name} : {taille_o//1024} Ko → {taille_n//1024} Ko (-{ratio:.0f}%)",
                icon="✅"
            )
        except Exception as e:
            st.error(f"Erreur traitement {f.name} : {e}")

    if not multipart:
        return []

    # PocketBase : update PATCH avec multipart/form-data, le serveur ajoute aux files existants
    r = requests.patch(
        f"{POCKETBASE_URL}/api/collections/agenda/records/{record_id}",
        headers=pb._headers(),
        files=multipart,
        timeout=120
    )
    if r.status_code != 200:
        st.error(f"Erreur upload : {r.status_code} - {r.text[:300]}")
        return []

    data = r.json()
    return data.get("images", [])

# =========================================================
# ACCES DATA (avec cache)
# =========================================================

@st.cache_data(ttl=60, show_spinner="Chargement des activités...")
def lire_activites() -> pd.DataFrame:
    try:
        # On essaie avec le tri PocketBase, sinon on tri cote python
        try:
            items = pb.list_all("agenda", sort="date,debut")
        except Exception:
            items = pb.list_all("agenda")
    except Exception as e:
        st.error(f"Erreur lecture PocketBase (agenda) : {e}")
        return pd.DataFrame()

    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    # Tri cote pandas (au cas ou le tri serveur a echoue)
    if "date" in df.columns and "debut" in df.columns:
        df = df.sort_values(["date", "debut"])
    df["heures"] = df.apply(calc_heures, axis=1)
    return df

@st.cache_data(ttl=30, show_spinner=False)
def lire_taches() -> list:
    """Lit toutes les taches sans tri serveur (tri en local)."""
    try:
        # Aucun parametre fancy : juste page/perPage
        all_items = []
        page = 1
        while True:
            r = requests.get(
                f"{POCKETBASE_URL}/api/collections/taches/records",
                params={"page": page, "perPage": 200},
                headers=pb._headers(),
                timeout=30
            )
            if r.status_code != 200:
                st.error(
                    f"Erreur lecture PocketBase (taches) : "
                    f"{r.status_code} - {r.text[:200]}"
                )
                return []
            data = r.json()
            all_items.extend(data.get("items", []))
            if page >= data.get("totalPages", 1):
                break
            page += 1

        # Tri cote python : non terminees d'abord
        def sort_key(t):
            done = bool(t.get("done", False))
            crea = t.get("created") or ""
            return (done, crea)
        all_items = sorted(all_items, key=sort_key, reverse=False)
        # Inverser pour avoir les plus recentes en premier (parmi les non-terminees)
        non_done = [t for t in all_items if not t.get("done")]
        done = [t for t in all_items if t.get("done")]
        non_done.reverse()
        done.reverse()
        return non_done + done
    except Exception as e:
        st.error(f"Erreur lecture PocketBase (taches) : {e}")
        return []

def invalider_cache():
    lire_activites.clear()
    lire_taches.clear()

# =========================================================
# SESSION STATE INIT
# =========================================================

def init_state():
    defaults = {
        "page": "📅 Calendrier",
        "search_text": "",
        "filter_tech": "Tous",
        "filter_date_debut": None,
        "filter_date_fin":   None,
        "page_num": 1,
        "upload_key": 0,
        "zoom_image": None,
        "zone_selectionnee": None,
        "calendar_version": 0,
        "last_event_click": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

# =========================================================
# DIALOGS (POPUPS)
# =========================================================

@st.dialog("🖼️ Image en grand", on_dismiss="rerun")
def dlg_zoom_image(url: str):
    st.image(url, width="stretch")
    if st.button("Fermer", width="stretch"):
        st.rerun()

@st.dialog("📋 Détails activité", on_dismiss="rerun")
def dlg_details_activite(row: dict):
    st.subheader("📄 Description")
    st.code(row.get("description", ""))

    c1, c2 = st.columns(2)
    c1.write(f"📅 **Date** : {format_date_fr(row.get('date', ''))}")
    c1.write(f"⏰ **Horaire** : {row.get('debut', '')} → {row.get('fin', '')}")
    c2.write(f"👷 **Technicien** : {row.get('technicien', 'Non défini')}")
    c2.write(f"🎨 **Couleur** : `{row.get('color', '')}`")

    # Construire les URLs d'images depuis le champ "images" de PocketBase
    record_id = row["id"]
    images_files = row.get("images", []) or []
    if isinstance(images_files, str):
        images_files = [images_files] if images_files else []

    # URLs depuis le champ "images" (vraies images dans PocketBase)
    imgs = [
        f"{POCKETBASE_URL}/api/files/agenda/{record_id}/{name}"
        for name in images_files
    ]
    # Ajouter aussi les URLs externes encore presentes dans image_url
    imgs += parse_images(row.get("image_url"))

    # Deduplication conservant l'ordre
    seen = set()
    imgs = [x for x in imgs if not (x in seen or seen.add(x))]

    if imgs:
        st.subheader(f"🖼️ Photos ({len(imgs)})")
        cols = st.columns(min(len(imgs), 3))
        for i, img in enumerate(imgs):
            with cols[i % 3]:
                st.image(img, width="stretch")
                if st.button("🔍 Zoom", key=f"zoom_{record_id}_{i}"):
                    st.session_state.zoom_image = img
                    st.rerun()

    st.divider()
    c1, c2, c3 = st.columns(3)
    if c1.button("✏️ Modifier", width="stretch"):
        st.session_state.edit_row = row
        st.rerun()
    if c2.button("🗑️ Supprimer", width="stretch"):
        st.session_state.delete_id = row["id"]
        st.rerun()
    if c3.button("Fermer", width="stretch"):
        st.rerun()

@st.dialog("🗑️ Confirmer la suppression", on_dismiss="rerun")
def dlg_confirm_delete(activite_id):
    st.warning("Cette action est **irréversible**. Supprimer cette activité ?")
    c1, c2 = st.columns(2)
    if c1.button("✅ Oui, supprimer", width="stretch"):
        try:
            pb.delete_record("agenda", activite_id)
            invalider_cache()
            st.session_state.calendar_version = st.session_state.get("calendar_version", 0) + 1
            st.session_state.pop("last_event_click", None)
            st.success("Activité supprimée")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("❌ Annuler", width="stretch"):
        st.rerun()

def _form_activite(row=None):
    """Formulaire partage entre ajout et edition."""
    is_edit = row is not None

    default_date  = pd.to_datetime(row["date"]).date() if is_edit and row.get("date") else date.today()
    default_debut = datetime.strptime(row["debut"], "%H:%M:%S").time() if is_edit and row.get("debut") else time(8, 0)
    default_fin   = datetime.strptime(row["fin"],   "%H:%M:%S").time() if is_edit and row.get("fin")   else time(9, 0)
    default_desc  = row.get("description", "") if is_edit else ""
    default_tech  = row.get("technicien", "MAT") if is_edit else "MAT"
    default_color = (row.get("color") if is_edit else None) or COULEUR_TECH.get(default_tech, "#00ff9c")

    d = st.date_input("📅 Date", value=default_date, format="DD/MM/YYYY")
    c1, c2 = st.columns(2)
    h_debut = c1.time_input("⏰ Début", value=default_debut)
    h_fin   = c2.time_input("⏰ Fin",   value=default_fin)

    desc = st.text_area("📄 Description", value=default_desc, height=120)

    c1, c2 = st.columns(2)
    tech  = c1.selectbox("👷 Technicien", TECHNICIENS,
                         index=TECHNICIENS.index(default_tech) if default_tech in TECHNICIENS else 0)
    color = c2.color_picker("🎨 Couleur", default_color)

    # Images existantes : depuis le champ "images" de PocketBase
    images_existantes_files = row.get("images", []) if is_edit else []
    if isinstance(images_existantes_files, str):
        images_existantes_files = [images_existantes_files] if images_existantes_files else []

    record_id_edit = row.get("id") if is_edit else None

    images_a_garder = []
    if images_existantes_files:
        st.markdown("**Images existantes** (décoche pour supprimer)")
        cols = st.columns(min(len(images_existantes_files), 3))
        for i, img_name in enumerate(images_existantes_files):
            url = f"{POCKETBASE_URL}/api/files/agenda/{record_id_edit}/{img_name}"
            with cols[i % 3]:
                st.image(url, width="stretch")
                garder = st.checkbox("Garder", value=True, key=f"keep_img_{i}")
                if garder:
                    images_a_garder.append(img_name)

    nouvelles_images = st.file_uploader(
        "📤 Ajouter des images (compressées automatiquement)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.upload_key}",
        help=f"Redimensionne a {COMPRESS_MAX_DIM}px max, JPEG qualite {COMPRESS_QUALITY}."
    )

    st.divider()
    c1, c2 = st.columns(2)
    submit_label = "💾 Enregistrer" if is_edit else "➕ Ajouter"
    if c1.button(submit_label, width="stretch", type="primary"):
        if not desc.strip():
            st.error("Description obligatoire")
            return
        if h_fin <= h_debut:
            st.error("L'heure de fin doit être après l'heure de début")
            return

        payload = {
            "date":        d.isoformat(),
            "debut":       h_debut.strftime("%H:%M:%S"),
            "fin":         h_fin.strftime("%H:%M:%S"),
            "description": desc.strip(),
            "technicien":  tech,
            "color":       color,
        }

        try:
            if is_edit:
                # En mode edit : on indique quelles images on garde (PocketBase remplace la liste)
                # Puis on ajoute les nouvelles via un PATCH multipart separe
                payload_keep = dict(payload)
                payload_keep["images"] = images_a_garder

                # Si on a des nouvelles images, on doit envoyer en multipart
                if nouvelles_images:
                    multipart = []
                    for f in nouvelles_images:
                        try:
                            content_origine = f.getvalue()
                            taille_o = len(content_origine)
                            content = compresser_bytes(content_origine)
                            taille_n = len(content)
                            base = f.name.rsplit(".", 1)[0]
                            filename = f"{base}.jpg"
                            multipart.append(("images", (filename, content, "image/jpeg")))
                            ratio = (1 - taille_n / taille_o) * 100 if taille_o else 0
                            st.toast(
                                f"📦 {f.name} : {taille_o//1024} Ko → {taille_n//1024} Ko (-{ratio:.0f}%)",
                                icon="✅"
                            )
                        except Exception as e:
                            st.error(f"Erreur traitement {f.name} : {e}")

                    # En multipart, on doit aussi envoyer les images a garder via "images" champ multiple
                    # PocketBase remplace la liste : on doit donc renvoyer aussi les noms gardes
                    form_data = {k: v for k, v in payload.items()}
                    # Trick : pour conserver les anciennes + ajouter, on utilise le champ "images+" si v0.23+
                    # Sinon, on fait un update JSON d'abord (filtrant les images a garder),
                    # puis un PATCH multipart avec les nouvelles seulement (qui s'ajoutent)
                    pb.update_record("agenda", row["id"], payload_keep)  # met a jour les champs + filtre images gardees

                    # PATCH multipart pour ajouter les nouvelles
                    r = requests.patch(
                        f"{POCKETBASE_URL}/api/collections/agenda/records/{row['id']}",
                        headers=pb._headers(),
                        files=multipart,
                        timeout=120
                    )
                    if r.status_code != 200:
                        st.error(f"Erreur upload images : {r.status_code} - {r.text[:300]}")
                        return
                else:
                    # Pas de nouvelles images : juste update JSON avec la liste filtree
                    pb.update_record("agenda", row["id"], payload_keep)

                st.success("Activité modifiée ✅")
            else:
                # Creation : un seul appel multipart si des images, sinon JSON
                if nouvelles_images:
                    multipart = []
                    for f in nouvelles_images:
                        try:
                            content_origine = f.getvalue()
                            taille_o = len(content_origine)
                            content = compresser_bytes(content_origine)
                            taille_n = len(content)
                            base = f.name.rsplit(".", 1)[0]
                            filename = f"{base}.jpg"
                            multipart.append(("images", (filename, content, "image/jpeg")))
                            ratio = (1 - taille_n / taille_o) * 100 if taille_o else 0
                            st.toast(
                                f"📦 {f.name} : {taille_o//1024} Ko → {taille_n//1024} Ko (-{ratio:.0f}%)",
                                icon="✅"
                            )
                        except Exception as e:
                            st.error(f"Erreur traitement {f.name} : {e}")

                    pb.create_record("agenda", payload, files=multipart)
                else:
                    pb.create_record("agenda", payload)

                send_push(desc, d.strftime("%d/%m/%Y"),
                          h_debut.strftime("%H:%M"), h_fin.strftime("%H:%M"), tech)
                st.success("Activité ajoutée ✅")

            invalider_cache()
            st.session_state.upload_key += 1
            st.session_state.calendar_version = st.session_state.get("calendar_version", 0) + 1
            st.session_state.pop("last_event_click", None)
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("Annuler", width="stretch"):
        st.rerun()

@st.dialog("➕ Ajouter une activité", width="large", on_dismiss="rerun")
def dlg_ajout():
    _form_activite()

@st.dialog("✏️ Modifier l'activité", width="large", on_dismiss="rerun")
def dlg_edit(row):
    _form_activite(row)

@st.dialog("📝 Tâches à prévoir", width="large", on_dismiss="rerun")
def dlg_taches():
    taches = lire_taches()

    with st.form("form_ajout_tache", clear_on_submit=True):
        c1, c2, c3 = st.columns([5, 2, 1])
        texte    = c1.text_input("Nouvelle tâche", label_visibility="collapsed",
                                 placeholder="Décrire la tâche...")
        priorite = c2.selectbox("Priorité", ["basse", "normale", "haute"],
                                index=1, label_visibility="collapsed")
        ajouter  = c3.form_submit_button("➕")
        if ajouter and texte.strip():
            try:
                pb.create_record("taches", {
                    "texte": texte.strip(),
                    "priorite": priorite,
                    "done": False,
                })
                lire_taches.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

    st.divider()

    if not taches:
        st.info("Aucune tâche. Ajoute-en une ci-dessus 👆")
        return

    show_done = st.checkbox("Afficher aussi les tâches terminées",
                            value=False, key="show_done_taches")
    taches_aff = taches if show_done else [t for t in taches if not t.get("done")]

    ordre_prio = {"haute": 0, "normale": 1, "basse": 2}
    taches_aff = sorted(taches_aff,
                        key=lambda t: (t.get("done", False),
                                       ordre_prio.get(t.get("priorite"), 1)))

    emoji_prio = {"haute": "🔴", "normale": "🟡", "basse": "🟢"}

    for t in taches_aff:
        c1, c2, c3 = st.columns([1, 8, 1])
        with c1:
            done = st.checkbox("✓", value=t.get("done", False),
                               key=f"task_done_{t['id']}",
                               label_visibility="collapsed")
            if done != t.get("done", False):
                try:
                    update = {"done": done,
                              "done_at": datetime.now().isoformat() if done else ""}
                    pb.update_record("taches", t["id"], update)
                    lire_taches.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")
        with c2:
            prio = t.get("priorite", "normale")
            texte_aff = t.get("texte", "")
            if t.get("done"):
                st.markdown(f"{emoji_prio.get(prio,'')} ~~{texte_aff}~~")
            else:
                st.markdown(f"{emoji_prio.get(prio,'')} **{texte_aff}**")
        with c3:
            if st.button("🗑️", key=f"task_del_{t['id']}"):
                try:
                    pb.delete_record("taches", t["id"])
                    lire_taches.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.divider()
    nb_restant = sum(1 for t in taches if not t.get("done"))
    st.caption(f"📌 {nb_restant} tâche(s) en cours • {len(taches)} au total")

# =========================================================
# DECLENCHEMENT POPUPS (un seul a la fois)
# =========================================================

_dialog_opened = False

if not _dialog_opened and st.session_state.get("zoom_image"):
    _dialog_opened = True
    img = st.session_state.pop("zoom_image")
    dlg_zoom_image(img)

if not _dialog_opened and st.session_state.get("delete_id"):
    _dialog_opened = True
    did = st.session_state.pop("delete_id")
    dlg_confirm_delete(did)

if not _dialog_opened and st.session_state.get("edit_row"):
    _dialog_opened = True
    er = st.session_state.pop("edit_row")
    dlg_edit(er)

if not _dialog_opened and st.session_state.get("show_add"):
    _dialog_opened = True
    st.session_state.pop("show_add", None)
    dlg_ajout()

if not _dialog_opened and st.session_state.get("details_row"):
    _dialog_opened = True
    dr = st.session_state.pop("details_row")
    dlg_details_activite(dr)

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.title("🧠 MAT AGENDA")

    page = st.radio(
        "Navigation",
        ["📅 Calendrier", "📂 Liste", "📊 Statistiques", "🏭 Plan Usine"],
        key="page"
    )

    st.divider()

    if st.button("➕ Ajouter activité", width="stretch", type="primary"):
        st.session_state.show_add = True
        st.rerun()

    if st.button("📝 Tâches à prévoir", width="stretch"):
        dlg_taches()

    st.divider()

    if st.button("🔄 Actualiser", width="stretch"):
        invalider_cache()
        st.toast("Données rechargées", icon="✅")
        st.rerun()

    try:
        nb_open = sum(1 for t in lire_taches() if not t.get("done"))
        if nb_open:
            st.caption(f"📌 {nb_open} tâche(s) en cours")
    except Exception:
        pass

    st.divider()

    # Bouton de deconnexion
    if st.button("🔓 Déconnexion", width="stretch"):
        st.session_state.auth_ok = False
        st.rerun()

    st.caption(f"🟢 Connecté à PocketBase")

# =========================================================
# LECTURE DATA GLOBALE
# =========================================================

df = lire_activites()

# =========================================================
# PAGE CALENDRIER
# =========================================================

if page == "📅 Calendrier":
    st.header("📅 Calendrier")

    if df.empty:
        st.info("Aucune activité. Clique sur ➕ Ajouter activité dans la barre latérale.")
    else:
        c1, _ = st.columns([2, 6])
        tech_filter = c1.selectbox(
            "Filtrer par technicien",
            ["Tous"] + TECHNICIENS,
            index=0, key="cal_tech_filter"
        )

        df_cal = df if tech_filter == "Tous" else df[df["technicien"] == tech_filter]

        events = []
        for _, row in df_cal.iterrows():
            raw_title = str(row.get("description", "")).split("\n")[0]
            title = (raw_title[:37] + "...") if len(raw_title) > 40 else raw_title
            events.append({
                "id":    str(row["id"]),
                "title": title,
                "start": f"{row['date']}T{row['debut']}",
                "end":   f"{row['date']}T{row['fin']}",
                "color": row.get("color") or COULEUR_TECH.get(row.get("technicien"), "#00ff9c"),
            })

        cal_key = f"calendar_{st.session_state.get('calendar_version', 0)}"

        state = calendar(
            events=events,
            options={
                "locale": "fr",
                "firstDay": 1,
                "timeZone": "local",
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay"
                },
                "buttonText": {
                    "today": "Aujourd'hui",
                    "month": "Mois",
                    "week":  "Semaine",
                    "day":   "Jour"
                }
            },
            callbacks=["eventClick"],
            key=cal_key,
        )

        if state and state.get("eventClick"):
            event_click = state["eventClick"]
            click_signature = f"{event_click['event']['id']}_{event_click.get('view', {}).get('currentStart', '')}"

            if st.session_state.get("last_event_click") != click_signature:
                st.session_state.last_event_click = click_signature
                event_id = event_click["event"]["id"]
                match = df[df["id"].astype(str) == str(event_id)]
                if not match.empty:
                    st.session_state.details_row = match.iloc[0].to_dict()
                    st.rerun()

# =========================================================
# PAGE LISTE
# =========================================================

elif page == "📂 Liste":
    st.header("📂 Activités")

    if df.empty:
        st.info("Aucune activité")
    else:
        with st.expander("🔍 Filtres", expanded=True):
            c1, c2, c3 = st.columns(3)
            search_text = c1.text_input(
                "Mot clé (description)",
                value=st.session_state.search_text
            )
            tech_filter = c2.selectbox(
                "Technicien",
                ["Tous"] + TECHNICIENS,
                index=(["Tous"] + TECHNICIENS).index(st.session_state.filter_tech)
                    if st.session_state.filter_tech in (["Tous"] + TECHNICIENS) else 0
            )
            c3.write("")
            c3.write("")
            reset = c3.button("♻️ Reset filtres", width="stretch")

            c1, c2 = st.columns(2)
            date_min_dispo = pd.to_datetime(df["date"]).min().date()
            date_max_dispo = pd.to_datetime(df["date"]).max().date()
            date_debut = c1.date_input(
                "Du",
                value=st.session_state.filter_date_debut or date_min_dispo,
                format="DD/MM/YYYY"
            )
            date_fin = c2.date_input(
                "Au",
                value=st.session_state.filter_date_fin or date_max_dispo,
                format="DD/MM/YYYY"
            )

        if reset:
            st.session_state.search_text = ""
            st.session_state.filter_tech = "Tous"
            st.session_state.filter_date_debut = None
            st.session_state.filter_date_fin   = None
            st.session_state.page_num = 1
            st.rerun()

        st.session_state.search_text = search_text
        st.session_state.filter_tech = tech_filter
        st.session_state.filter_date_debut = date_debut
        st.session_state.filter_date_fin   = date_fin

        sub = df.copy()

        # --- Filtres ---
        if search_text:
            for mot in search_text.split():
                sub = sub[sub["description"].astype(str)
                         .str.contains(mot, case=False, na=False)]

        if tech_filter != "Tous":
            sub = sub[sub["technicien"] == tech_filter]

        sub = sub[
            (pd.to_datetime(sub["date"]).dt.date >= date_debut) &
            (pd.to_datetime(sub["date"]).dt.date <= date_fin)
        ]

        # --- TRI CHRONOLOGIQUE DÉCROISSANT ---
        sub = sub.sort_values(by=["date", "debut"], ascending=False)

        # --- Résumé ---
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.caption(
            f"📊 **{len(sub)}** activité(s) • "
            f"⏱ **{round(sub['heures'].sum(), 1)} h** cumulées"
        )

        if not sub.empty:
            csv = sub.drop(columns=["heures", "images"], errors="ignore").to_csv(index=False)
            c3.download_button(
                "📥 Export CSV",
                data=csv,
                file_name=f"mat_agenda_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch"
            )

        if sub.empty:
            st.info("Aucune activité trouvée avec ces filtres")
        else:
            PAR_PAGE = 10
            nb_pages = max(1, (len(sub) + PAR_PAGE - 1) // PAR_PAGE)
            st.session_state.page_num = min(st.session_state.page_num, nb_pages)

            c1, c2, c3 = st.columns([1, 2, 1])
            if c1.button("⬅️ Précédent", disabled=st.session_state.page_num <= 1):
                st.session_state.page_num -= 1
                st.rerun()

            c2.markdown(
                f"<p style='text-align:center'>Page "
                f"<b>{st.session_state.page_num}</b> / {nb_pages}</p>",
                unsafe_allow_html=True
            )

            if c3.button("Suivant ➡️", disabled=st.session_state.page_num >= nb_pages):
                st.session_state.page_num += 1
                st.rerun()

            debut_idx = (st.session_state.page_num - 1) * PAR_PAGE
            fin_idx   = debut_idx + PAR_PAGE

            for _, row in sub.iloc[debut_idx:fin_idx].iterrows():
                with st.container():
                    st.markdown('<div class="activity-card">', unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([7, 1, 1])

                    with c1:
                        st.markdown(
                            f"**📅 {format_date_fr(row['date'])}** • "
                            f"⏰ {row['debut'][:5]} → {row['fin'][:5]} • "
                            f"👷 {row.get('technicien', 'Non défini')} • "
                            f"⏱ {row['heures']:.1f} h"
                        )
                        with st.expander("Voir détails"):
                            st.code(row["description"])

                            record_id = row["id"]
                            imgs_files = row.get("images", []) or []
                            if isinstance(imgs_files, str):
                                imgs_files = [imgs_files] if imgs_files else []

                            imgs = [
                                f"{POCKETBASE_URL}/api/files/agenda/{record_id}/{n}"
                                for n in imgs_files
                            ]
                            imgs += parse_images(row.get("image_url"))

                            seen = set()
                            imgs = [x for x in imgs if not (x in seen or seen.add(x))]

                            if imgs:
                                cols = st.columns(min(len(imgs), 4))
                                for i, img in enumerate(imgs):
                                    cols[i % 4].image(img, width="stretch")

                    with c2:
                        if st.button("✏️", key=f"edit_{row['id']}"):
                            st.session_state.edit_row = row.to_dict()
                            st.rerun()

                    with c3:
                        if st.button("🗑️", key=f"del_{row['id']}"):
                            st.session_state.delete_id = row["id"]
                            st.rerun()

                    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# PAGE STATISTIQUES
# =========================================================

elif page == "📊 Statistiques":
    st.header("📊 Statistiques")

    if df.empty:
        st.info("Pas de données")
    else:
        c1, c2 = st.columns([2, 6])
        tech_filter = c1.selectbox(
            "👷 Technicien",
            ["Tous"] + sorted(df["technicien"].dropna().unique())
        )
        sub = df if tech_filter == "Tous" else df[df["technicien"] == tech_filter]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⏱ Temps total", f"{sub['heures'].sum():.1f} h")
        c2.metric("📅 Activités",   len(sub))
        c3.metric("📊 Moyenne",     f"{sub['heures'].mean():.1f} h" if len(sub) else "—")
        nb_jours = sub["date"].nunique() if len(sub) else 0
        c4.metric("🗓️ Jours actifs", nb_jours)

        st.divider()

        sub = sub.copy()
        sub["mois"] = pd.to_datetime(sub["date"]).dt.strftime("%Y-%m")
        stats_mois = sub.groupby("mois")["heures"].sum().sort_index()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Heures par mois")
            st.bar_chart(stats_mois, color="#00ff9c")

        with c2:
            st.subheader("Répartition par technicien")
            stats_tech = df.groupby("technicien")["heures"].sum().sort_values(ascending=False)
            if len(stats_tech) > 0:
                st.bar_chart(stats_tech, color="#00ffee")

        st.subheader("Nombre d'activités par mois")
        stats_nb = sub.groupby("mois").size()
        st.line_chart(stats_nb, color="#00ffee")

# =========================================================
# PAGE PLAN USINE
# =========================================================

elif page == "🏭 Plan Usine":
    st.header("🏭 Plan Usine")

    ZONES = {
        "01": (1011,180,1098,244),  "02": (945,180,1009,242),
        "03": (935,242,1009,293),   "04": (1234,129,1310,208),
        "05": (1234,205,1310,272),  "06": (585,215,682,254),
        "07": (422,699,533,786),    "08": (1234,440,1404,571),
        "09": (1234,571,1404,692),  "10": (584,414,711,488),
        "12": (263,150,334,224),    "14": (263,224,421,312),
        "15": (533,179,585,879),    "26": (1234,313,1404,440),
        "27": (1234,692,1404,783),  "28": (289,795,467,879),
        "29": (584,612,663,680),    "30": (584,180,679,215),
        "31": (584,680,663,769),    "32": (832,180,947,242),
        "33": (791,83,1029,179),    "36": (382,80,443,224),
        "37": (681,256,788,333),    "38": (1019,795,1179,872),
        "39": (1024,438,1086,608),  "40": (873,795,1019,872),
        "42": (1086,612,1175,696),  "44": (740,292,1030,329),
        "45": (663,811,797,876),    "46": (903,438,1024,608),
        "47": (832,242,889,291),    "49": (889,242,935,291),
        "53": (584,488,771,610),    "101": (373,314,530,693),
        "102": (1104,126,1404,272), "103": (584,311,682,413),
        "104": (584,83,788,180),    "105": (726,435,881,553),
        "106": (681,333,793,488),   "107": (663,612,796,679),
        "108": (1048,337,1116,391), "109": (1005,337,1051,391),
        "110": (193,314,375,791),   "111": (1086,443,1175,612),
        "117": (663,680,791,766),
    }

    @st.cache_data(ttl=60)
    def compter_par_zone(machines: tuple) -> dict:
        out = {}
        if df.empty:
            return {m: 0 for m in machines}
        desc = df["description"].astype(str).str.lower()
        for m in machines:
            out[m] = int(desc.str.contains(f"zone {m}", regex=False).sum())
        return out

    counts = compter_par_zone(tuple(ZONES.keys()))

    c1, c2 = st.columns([3, 2])
    with c1:
        st.caption("Clique une zone sur le plan, ou sélectionne directement :")
    with c2:
        def sort_key(m):
            try:  return (0, int(m))
            except: return (1, m)
        zones_options = sorted(ZONES.keys(), key=sort_key)

        choix = st.selectbox(
            "Zone",
            options=[""] + zones_options,
            format_func=lambda z: "— Choisir —" if z == "" else
                f"Zone {z}  ({counts.get(z,0)} activité{'s' if counts.get(z,0)>1 else ''})",
            label_visibility="collapsed",
            key="zone_select"
        )
        if choix:
            st.session_state.zone_selectionnee = choix

    try:
        image = Image.open("Plan_usine.png")
        click = streamlit_image_coordinates(image, key="plan", width=image.width)

        if click:
            x, y = click["x"], click["y"]
            for machine, (x1, y1, x2, y2) in ZONES.items():
                if x1 <= x <= x2 and y1 <= y <= y2:
                    st.session_state.zone_selectionnee = machine
                    break
            else:
                st.warning(f"📍 Aucune machine à cette position ({x}, {y})")

    except FileNotFoundError:
        st.error("❌ Fichier `Plan_usine.png` introuvable")

    zone = st.session_state.zone_selectionnee
    if zone:
        st.divider()
        st.success(f"🟩 Zone sélectionnée : **{zone}**")

        if df.empty:
            st.info("Aucune activité")
        else:
            mask = df["description"].astype(str).str.contains(
                f"zone {zone}", case=False, regex=False, na=False
            )
            zone_df = df[mask].sort_values("date", ascending=False)

            if zone_df.empty:
                st.info(f"Aucune activité pour la zone {zone}")
            else:
                st.caption(f"📊 {len(zone_df)} activité(s) trouvée(s) • "
                           f"⏱ {zone_df['heures'].sum():.1f} h cumulées")

                for _, row in zone_df.iterrows():
                    with st.container():
                        st.markdown('<div class="activity-card">', unsafe_allow_html=True)
                        c1, c2, c3 = st.columns([7, 1, 1])
                        with c1:
                            st.markdown(
                                f"**📅 {format_date_fr(row['date'])}** • "
                                f"⏰ {row['debut'][:5]} → {row['fin'][:5]} • "
                                f"👷 {row.get('technicien', 'Non défini')}"
                            )
                            with st.expander("Voir détails"):
                                st.code(row["description"])
                                record_id = row["id"]
                                imgs_files = row.get("images", []) or []
                                if isinstance(imgs_files, str):
                                    imgs_files = [imgs_files] if imgs_files else []
                                imgs = [
                                    f"{POCKETBASE_URL}/api/files/agenda/{record_id}/{n}"
                                    for n in imgs_files
                                ]
                                imgs += parse_images(row.get("image_url"))
                                seen = set()
                                imgs = [x for x in imgs if not (x in seen or seen.add(x))]
                                if imgs:
                                    cols = st.columns(min(len(imgs), 4))
                                    for i, img in enumerate(imgs):
                                        cols[i % 4].image(img, width="stretch")
                        with c2:
                            if st.button("✏️", key=f"zone_edit_{row['id']}"):
                                st.session_state.edit_row = row.to_dict()
                                st.rerun()
                        with c3:
                            if st.button("🗑️", key=f"zone_del_{row['id']}"):
                                st.session_state.delete_id = row["id"]
                                st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)
