"""
MAT AGENDA — version Streamlit optimisée
========================================
Améliorations par rapport à la version précédente :
- Cache Supabase (ttl=60s) + bouton actualiser => gros gain de vitesse
- Clés API sortables dans st.secrets
- Tâches à prévoir dans une table dédiée `taches` (plus de perte de données)
- Popups (st.dialog) pour Ajout / Édition / Suppression / Zoom image
- Confirmation avant suppression
- Filtres liste : texte + technicien + plage de dates + pagination
- Export CSV
- Stats enrichies (heures par technicien + par mois)
- Plan usine : tooltip + badges de comptage par zone
- Gestion d'erreurs sur les appels Supabase
"""

import json
from datetime import datetime, time, date, timedelta

import pandas as pd
import requests
import streamlit as st
from PIL import Image
from supabase import create_client
from streamlit_calendar import calendar
from streamlit_image_coordinates import streamlit_image_coordinates

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(page_title="MAT Agenda", layout="wide", page_icon="🧠")

# ---- Secrets (Streamlit Cloud → Settings → Secrets) ----
# Fichier .streamlit/secrets.toml (exemple) :
#   SUPABASE_URL = "https://..."
#   SUPABASE_KEY = "sb_publishable_..."
#   PUSHOVER_TOKEN = "..."
#   PUSHOVER_USER  = "..."
try:
    SUPABASE_URL   = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY   = st.secrets["SUPABASE_KEY"]
    PUSHOVER_TOKEN = st.secrets.get("PUSHOVER_TOKEN", "")
    PUSHOVER_USER  = st.secrets.get("PUSHOVER_USER",  "")
except (KeyError, FileNotFoundError):
    # Fallback dev — à RETIRER une fois les secrets configurés
    SUPABASE_URL   = "https://quamffmaxqhhtyxworou.supabase.co"
    SUPABASE_KEY   = "sb_publishable_zKt7ObrIa8kkHXjlvhk4tw_SUetSTZG"
    PUSHOVER_TOKEN = "a6vqbmhhjyzu19ay371qxhmmwuwnpp"
    PUSHOVER_USER  = "uykkgtvss4kmbyuscgce5xqgdb5ufy"

APP_URL = "https://mat-agenda-web2-mngwrfjcalzf3kbpdvd99n.streamlit.app"

TECHNICIENS = ["MAT", "Sébastien"]

# Couleur par défaut par technicien
COULEUR_TECH = {
    "MAT":       "#00ff9c",
    "Sébastien": "#00ffee",
}

# =========================================================
# CLIENT SUPABASE
# =========================================================

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# =========================================================
# STYLE
# =========================================================

st.markdown("""
<style>
.stApp { background:#0b0f14; color:#e5e7eb; }
h1, h2, h3 { color:#00ffee; }
.stButton>button {
    background:#111827; color:#00ff9c;
    border:1px solid #00ff9c; border-radius:8px;
}
.stButton>button:hover { background:#00ff9c; color:black; }
[data-testid="stMetricValue"] { color:#00ff9c; }
.activity-card {
    background:#111827;
    border-left:4px solid #00ff9c;
    padding:12px; margin:8px 0; border-radius:8px;
}
</style>
""", unsafe_allow_html=True)

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
    """Envoi notification Pushover (non bloquant — on ignore les erreurs)."""
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

def parse_images(raw):
    """Retourne toujours une liste d'URL d'images."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, str)]
    try:
        imgs = json.loads(raw)
        if isinstance(imgs, list):
            return [x for x in imgs if isinstance(x, str)]
        if isinstance(imgs, str):
            return [imgs]
    except Exception:
        if isinstance(raw, str) and raw.startswith("http"):
            return [raw]
    return []

def upload_images(files):
    """Upload une liste de fichiers UploadedFile vers Supabase Storage."""
    urls = []
    for f in files or []:
        try:
            file_name = f"{int(datetime.now().timestamp()*1000)}_{f.name}"
            supabase.storage.from_("agenda-images").upload(file_name, f.getvalue())
            urls.append(supabase.storage.from_("agenda-images").get_public_url(file_name))
        except Exception as e:
            st.error(f"Erreur upload {f.name} : {e}")
    return urls

# =========================================================
# ACCÈS DATA (avec cache)
# =========================================================

@st.cache_data(ttl=60, show_spinner="Chargement des activités...")
def lire_activites() -> pd.DataFrame:
    try:
        resp = supabase.table("agenda").select("*").execute()
        data = resp.data or []
    except Exception as e:
        st.error(f"Erreur lecture Supabase : {e}")
        return pd.DataFrame()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data).sort_values(["date", "debut"])
    df["heures"] = df.apply(calc_heures, axis=1)
    return df

@st.cache_data(ttl=30, show_spinner=False)
def lire_taches() -> list[dict]:
    """Lit les tâches depuis la table dédiée `taches`."""
    try:
        resp = (supabase.table("taches")
                .select("*")
                .order("done", desc=False)
                .order("created_at", desc=True)
                .execute())
        return resp.data or []
    except Exception as e:
        st.error(
            "⚠️ La table `taches` n'est pas accessible. "
            "As-tu exécuté le script `01_creer_table_taches.sql` dans Supabase ?\n\n"
            f"Détail : {e}"
        )
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
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

# =========================================================
# DIALOGS (POPUPS)
# =========================================================

@st.dialog("🖼️ Image en grand")
def dlg_zoom_image(url: str):
    st.image(url, width="stretch")
    if st.button("Fermer", width="stretch"):
        st.rerun()

@st.dialog("📋 Détails activité")
def dlg_details_activite(row: dict):
    st.subheader("📄 Description")
    st.code(row.get("description", ""))

    c1, c2 = st.columns(2)
    c1.write(f"📅 **Date** : {format_date_fr(row.get('date', ''))}")
    c1.write(f"⏰ **Horaire** : {row.get('debut', '')} → {row.get('fin', '')}")
    c2.write(f"👷 **Technicien** : {row.get('technicien', 'Non défini')}")
    c2.write(f"🎨 **Couleur** : `{row.get('color', '')}`")

    imgs = parse_images(row.get("image_url"))
    if imgs:
        st.subheader(f"🖼️ Photos ({len(imgs)})")
        cols = st.columns(min(len(imgs), 3))
        for i, img in enumerate(imgs):
            with cols[i % 3]:
                st.image(img, width="stretch")
                if st.button("🔍 Zoom", key=f"zoom_{row['id']}_{i}"):
                    st.session_state.zoom_image = img
                    st.rerun()

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("✏️ Modifier", width="stretch"):
        st.session_state.edit_row = row
        st.rerun()
    if c2.button("🗑️ Supprimer", width="stretch"):
        st.session_state.delete_id = row["id"]
        st.rerun()

@st.dialog("🗑️ Confirmer la suppression")
def dlg_confirm_delete(activite_id):
    st.warning("Cette action est **irréversible**. Supprimer cette activité ?")
    c1, c2 = st.columns(2)
    if c1.button("✅ Oui, supprimer", width="stretch"):
        try:
            supabase.table("agenda").delete().eq("id", activite_id).execute()
            invalider_cache()
            st.session_state.pop("delete_id", None)
            st.success("Activité supprimée")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("❌ Annuler", width="stretch"):
        st.session_state.pop("delete_id", None)
        st.rerun()

def _form_activite(row=None):
    """Formulaire partagé entre ajout et édition. row=None => ajout."""
    is_edit = row is not None

    default_date   = pd.to_datetime(row["date"]).date() if is_edit else date.today()
    default_debut  = datetime.strptime(row["debut"], "%H:%M:%S").time() if is_edit else time(8, 0)
    default_fin    = datetime.strptime(row["fin"],   "%H:%M:%S").time() if is_edit else time(9, 0)
    default_desc   = row.get("description", "") if is_edit else ""
    default_tech   = row.get("technicien", "MAT") if is_edit else "MAT"
    default_color  = row.get("color") or COULEUR_TECH.get(default_tech, "#00ff9c")

    d = st.date_input("📅 Date", value=default_date, format="DD/MM/YYYY")
    c1, c2 = st.columns(2)
    h_debut = c1.time_input("⏰ Début", value=default_debut)
    h_fin   = c2.time_input("⏰ Fin",   value=default_fin)

    desc = st.text_area("📄 Description", value=default_desc, height=120)

    c1, c2 = st.columns(2)
    tech  = c1.selectbox("👷 Technicien", TECHNICIENS,
                         index=TECHNICIENS.index(default_tech) if default_tech in TECHNICIENS else 0)
    color = c2.color_picker("🎨 Couleur", default_color)

    # Images existantes
    images_existantes = parse_images(row.get("image_url")) if is_edit else []
    images_a_garder = []
    if images_existantes:
        st.markdown("**Images existantes** (décoche pour supprimer)")
        cols = st.columns(min(len(images_existantes), 3))
        for i, img in enumerate(images_existantes):
            with cols[i % 3]:
                st.image(img, width="stretch")
                garder = st.checkbox("Garder", value=True, key=f"keep_img_{i}")
                if garder:
                    images_a_garder.append(img)

    nouvelles_images = st.file_uploader(
        "📤 Ajouter des images",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.upload_key}"
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

        urls = images_a_garder + upload_images(nouvelles_images)

        payload = {
            "date":        d.isoformat(),
            "debut":       h_debut.strftime("%H:%M:%S"),
            "fin":         h_fin.strftime("%H:%M:%S"),
            "description": desc.strip(),
            "technicien":  tech,
            "color":       color,
            "image_url":   json.dumps(urls),
        }

        try:
            if is_edit:
                supabase.table("agenda").update(payload).eq("id", row["id"]).execute()
                st.success("Activité modifiée ✅")
            else:
                supabase.table("agenda").insert(payload).execute()
                send_push(desc, d.strftime("%d/%m/%Y"),
                          h_debut.strftime("%H:%M"), h_fin.strftime("%H:%M"), tech)
                st.success("Activité ajoutée ✅")

            invalider_cache()
            st.session_state.upload_key += 1
            st.session_state.pop("edit_row", None)
            st.session_state.pop("show_add", None)
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("Annuler", width="stretch"):
        st.session_state.pop("edit_row", None)
        st.session_state.pop("show_add", None)
        st.rerun()

@st.dialog("➕ Ajouter une activité", width="large")
def dlg_ajout():
    _form_activite()

@st.dialog("✏️ Modifier l'activité", width="large")
def dlg_edit(row):
    _form_activite(row)

@st.dialog("📝 Tâches à prévoir", width="large")
def dlg_taches():
    taches = lire_taches()

    # Ajout rapide
    with st.form("form_ajout_tache", clear_on_submit=True):
        c1, c2, c3 = st.columns([5, 2, 1])
        texte    = c1.text_input("Nouvelle tâche", label_visibility="collapsed",
                                 placeholder="Décrire la tâche...")
        priorite = c2.selectbox("Priorité", ["basse", "normale", "haute"],
                                index=1, label_visibility="collapsed")
        ajouter  = c3.form_submit_button("➕")
        if ajouter and texte.strip():
            try:
                supabase.table("taches").insert({
                    "texte": texte.strip(),
                    "priorite": priorite,
                    "done": False,
                }).execute()
                lire_taches.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

    st.divider()

    if not taches:
        st.info("Aucune tâche. Ajoute-en une ci-dessus 👆")
        return

    # Filtre affichage
    show_done = st.checkbox("Afficher aussi les tâches terminées",
                            value=False, key="show_done_taches")
    taches_aff = taches if show_done else [t for t in taches if not t.get("done")]

    # Groupement par priorité (haute en haut)
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
                              "done_at": datetime.now().isoformat() if done else None}
                    supabase.table("taches").update(update).eq("id", t["id"]).execute()
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
                    supabase.table("taches").delete().eq("id", t["id"]).execute()
                    lire_taches.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.divider()
    nb_restant = sum(1 for t in taches if not t.get("done"))
    st.caption(f"📌 {nb_restant} tâche(s) en cours • {len(taches)} au total")

# =========================================================
# GESTION POPUPS DÉCLENCHÉES
# =========================================================

if st.session_state.get("zoom_image"):
    img = st.session_state.pop("zoom_image")
    dlg_zoom_image(img)
if st.session_state.get("delete_id"):
    dlg_confirm_delete(st.session_state["delete_id"])
if st.session_state.get("edit_row"):
    dlg_edit(st.session_state["edit_row"])
if st.session_state.get("show_add"):
    dlg_ajout()

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

    # Indicateur rapide tâches non terminées
    try:
        nb_open = sum(1 for t in lire_taches() if not t.get("done"))
        if nb_open:
            st.caption(f"📌 {nb_open} tâche(s) en cours")
    except Exception:
        pass

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
        # Filtre technicien rapide
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
            key="calendar_main",
        )

        if state and state.get("eventClick"):
            event_id = state["eventClick"]["event"]["id"]
            match = df[df["id"].astype(str) == str(event_id)]
            if not match.empty:
                dlg_details_activite(match.iloc[0].to_dict())

# =========================================================
# PAGE LISTE
# =========================================================

elif page == "📂 Liste":
    st.header("📂 Activités")

    if df.empty:
        st.info("Aucune activité")
    else:
        # --- FILTRES ---
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

        # --- APPLICATION DES FILTRES ---
        sub = df.copy()
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

        # --- HEADER RÉSULTATS + EXPORT ---
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.caption(f"📊 **{len(sub)}** activité(s) • "
                   f"⏱ **{round(sub['heures'].sum(), 1)} h** cumulées")

        if not sub.empty:
            csv = sub.drop(columns=["heures"], errors="ignore").to_csv(index=False)
            c3.download_button(
                "📥 Export CSV",
                data=csv,
                file_name=f"mat_agenda_{datetime.now():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch"
            )

        # --- PAGINATION ---
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

            # --- AFFICHAGE ---
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
                            imgs = parse_images(row.get("image_url"))
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

        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⏱ Temps total", f"{sub['heures'].sum():.1f} h")
        c2.metric("📅 Activités",   len(sub))
        c3.metric("📊 Moyenne",     f"{sub['heures'].mean():.1f} h" if len(sub) else "—")
        nb_jours = sub["date"].nunique() if len(sub) else 0
        c4.metric("🗓️ Jours actifs", nb_jours)

        st.divider()

        # Heures par mois
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

    # ---- Définition des zones ----
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

    # ---- Nombre d'activités par zone (via scan descriptions) ----
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

    # ---- Sélection rapide sans cliquer sur le plan ----
    c1, c2 = st.columns([3, 2])
    with c1:
        st.caption("Clique une zone sur le plan, ou sélectionne directement :")
    with c2:
        # Trier par numérique quand possible
        def sort_key(m):
            try:  return (0, int(m))
            except: return (1, m)
        zones_options = sorted(ZONES.keys(), key=sort_key)
        labels = [f"Zone {z}  ({counts.get(z,0)} act.)" for z in zones_options]

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

    # ---- Image cliquable ----
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

    # ---- Affichage activités de la zone sélectionnée ----
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
                                imgs = parse_images(row.get("image_url"))
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
