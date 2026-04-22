import streamlit as st
import pandas as pd
import json
import requests
from datetime import datetime
from streamlit_calendar import calendar
from supabase import create_client

# =========================
# SUPABASE
# ========================
url = "https://quamffmaxqhhtyxworou.supabase.co"
key = "sb_publishable_zKt7ObrIa8kkHXjlvhk4tw_SUetSTZG"
supabase = create_client(url, key)

response = supabase.table("agenda").select("*").execute()
print(response.data)

# =========================
# CONFIGURATION PAGE
# =========================
st.set_page_config(layout="wide")
st.title("🧠 MAT AGENDA TXT")

# =========================
# STYLE
# =========================
st.markdown("""
<style>
.stApp{background:#0b0f14;color:#00ff9c;}
h1,h2,h3{color:#00ffee;}
.stButton>button{background:#00ff9c;color:black;border-radius:8px;}
</style>
""", unsafe_allow_html=True)

if "zoom_image" not in st.session_state:
    st.session_state.zoom_image = None

if "show_zoom" not in st.session_state:
    st.session_state.show_zoom = False
# =========================
# LECTURE SUPABASE
# =========================
def lire_data():
    response = supabase.table("agenda").select("*").execute()
    data = response.data
    return pd.DataFrame(data)

df = lire_data()

def format_date_fr(date_str):
    try:
        d = datetime.strptime(date_str,"%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except:
        return date_str

# =========================
# POPUP TACHES A PREVOIR
# =========================
@st.dialog("📝 Tâches à prévoir")
def popup_tasks():

    # lecture supabase
    response = supabase.table("agenda").select('id, "Tâches à prévoir"').limit(1).execute()

    tasks = []
    row_id = None

    if response.data:
        row_id = response.data[0]["id"]

        raw = response.data[0].get("Tâches à prévoir")

        if raw:
            try:
                tasks = json.loads(raw)
            except:
                tasks = []

    st.subheader("📋 Liste des tâches")

    new_tasks = []

    if tasks:
        for i, task in enumerate(tasks):

            col1, col2 = st.columns([6,1])

            with col1:
                st.write(f"• {task}")

            with col2:
                delete = st.button("❌", key=f"del_task_{i}")

            if not delete:
                new_tasks.append(task)
    else:
        st.info("Aucune tâche")

    # ajout
    st.subheader("➕ Ajouter une tâche")

    new_task = st.text_input("Nouvelle tâche")

    if st.button("Ajouter tâche"):
        if new_task.strip() and row_id:

            new_tasks.append(new_task)

            supabase.table("agenda").update({
                "Tâches à prévoir": json.dumps(new_tasks)
            }).eq("id", row_id).execute()

            st.rerun()

    # sauvegarde suppression
    if tasks != new_tasks and row_id:

        supabase.table("agenda").update({
            "Tâches à prévoir": json.dumps(new_tasks)
        }).eq("id", row_id).execute()

    if st.button("Fermer"):
        st.rerun()
        
# =========================
# NOTIFICATION
# =========================
def send_push(desc, date, debut, fin, tech):

    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": "a6vqbmhhjyzu19ay371qxhmmwuwnpp",
            "user": "uykkgtvss4kmbyuscgce5xqgdb5ufy",
            "title": "📅 Nouvelle activité",
            "message": f"{desc}\n📆 {date}\n⏰ {debut} → {fin}\n👷 {tech}",
            "url": "https://mat-agenda-web2-mngwrfjcalzf3kbpdvd99n.streamlit.app",
            "url_title": "📂 Ouvrir MAT Agenda"
        }
    )  
# =========================
# MODIFICATION ACTIVITE
# =========================
if "edit_id" in st.session_state:

    st.subheader("✏ Modifier activité")

    # ------------------------
    # CHAMPS PRINCIPAUX
    # ------------------------
    new_date = st.date_input(
        "📅 Date",
        value=pd.to_datetime(st.session_state["edit_date"]),
        format="DD/MM/YYYY"
    )

    new_debut = st.text_input("Début", st.session_state["edit_debut"])
    new_fin = st.text_input("Fin", st.session_state["edit_fin"])

    new_desc = st.text_area(
        "Description",
        value=st.session_state["edit_desc"]
    )

    # ------------------------
    # TECHNICIEN
    # ------------------------
    techniciens = ["MAT", "Sébastien"]

    tech_selected = st.selectbox(
        "🛠 Technicien",
        techniciens,
        index=techniciens.index(
            st.session_state.get("edit_technicien", "MAT")
        )
    )

    # ------------------------
    # COULEUR
    # ------------------------
    color = st.color_picker(
        "Couleur",
        st.session_state.get("edit_color", "#00ff9c")
    )

    # ------------------------
    # IMAGES EXISTANTES
    # ------------------------
    images = []

    if "edit_images" in st.session_state and st.session_state["edit_images"]:
        try:
            images = json.loads(st.session_state["edit_images"])
        except:
            images = []

    st.subheader("Images existantes")

    new_images_list = []

    for i, img in enumerate(images):

        col1, col2 = st.columns([5, 1])

        with col1:
            st.image(img, width=250)

        with col2:
            delete = st.checkbox("❌", key=f"delimg{i}")

        if not delete:
            new_images_list.append(img)

    # ------------------------
    # AJOUT NOUVELLES IMAGES
    # ------------------------
    new_uploads = st.file_uploader(
        "Ajouter nouvelles images",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    # ------------------------
    # SAVE
    # ------------------------
    if st.button("Enregistrer modification"):

        # Upload nouvelles images
        if new_uploads:
            for img in new_uploads:

                file_name = f"{int(datetime.now().timestamp()*1000)}_{img.name}"

                try:
                    supabase.storage.from_("agenda-images").upload(
                        file_name,
                        img.getvalue()
                    )

                    url = supabase.storage.from_("agenda-images").get_public_url(file_name)

                    new_images_list.append(url)

                except Exception as e:
                    st.error(f"Erreur upload {img.name}: {e}")

        # UPDATE SUPABASE
        supabase.table("agenda").update({
            "date": new_date.isoformat(),
            "debut": new_debut,
            "fin": new_fin,
            "description": new_desc,
            "technicien": tech_selected,
            "color": color,
            "image_url": json.dumps(new_images_list)
        }).eq("id", st.session_state["edit_id"]).execute()

        # CLEAN SESSION
        for key in [
            "edit_id",
            "edit_desc",
            "edit_date",
            "edit_debut",
            "edit_fin",
            "edit_images",
            "edit_technicien",
            "edit_color"
        ]:
            st.session_state.pop(key, None)

        st.success("✅ Activité modifiée")
        st.rerun()
# =========================
# NAVIGATION
# =========================
    
page = st.sidebar.radio(
    "Navigation",
    ["📅 Calendrier", "📂 Liste", "📊 Statistiques", "🏭 Plan Usine"]
)

if st.button("📝 Tâches à prévoir"):
    popup_tasks()

if "reset_sidebar" not in st.session_state:
    st.session_state.reset_sidebar = False

# =========================
# INIT SESSION STATE
# =========================
from datetime import datetime, time
import json

if "reset_sidebar" not in st.session_state:
    st.session_state.reset_sidebar = False

if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

# =========================
# RESET AVANT WIDGETS (OBLIGATOIRE)
# =========================
if st.session_state.reset_sidebar:
    st.session_state.sidebar_date = datetime.today()
    st.session_state.sidebar_debut = time(8, 0)
    st.session_state.sidebar_fin = time(9, 0)
    st.session_state.sidebar_description = ""
    st.session_state.sidebar_color = "#00ff9c"
    # ⚠️ pas de reset direct file_uploader ici

    st.session_state.reset_sidebar = False

# =========================
# SIDEBAR FORM
# =========================
st.sidebar.header("➕ Ajouter activité")

techniciens = ["MAT", "Sébastien"]

tech_selected = st.sidebar.selectbox(
    "🛠 Technicien",
    techniciens,
    key="sidebar_technicien"
)

date = st.sidebar.date_input(
    "📅 Date",
    format="DD/MM/YYYY",
    key="sidebar_date"
)

debut = st.sidebar.time_input("Début", key="sidebar_debut")
fin = st.sidebar.time_input("Fin", key="sidebar_fin")
desc = st.sidebar.text_area("Description", key="sidebar_description")
color = st.sidebar.color_picker("Couleur", "#00ff9c", key="sidebar_color")

# 🔥 FILE UPLOADER CORRIGÉ (clé dynamique)
images = st.sidebar.file_uploader(
    "Images activité",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key=f"sidebar_images_upload_{st.session_state.upload_key}"
)

# =========================
# BOUTON AJOUT
# =========================
if st.sidebar.button("Ajouter activité"):

    if not desc:
        st.sidebar.warning("Description obligatoire")

    else:
        image_urls = []

        if images:
            for image in images:
                try:
                    file_name = f"{int(datetime.now().timestamp()*1000)}_{image.name}"

                    supabase.storage.from_("agenda-images").upload(
                        file_name,
                        image.getvalue()
                    )

                    url = supabase.storage.from_("agenda-images").get_public_url(file_name)
                    image_urls.append(url)

                except Exception as e:
                    st.error(f"Erreur upload {image.name}: {e}")

        # =========================
        # INSERT DB
        # =========================
        supabase.table("agenda").insert({
            "date": date.isoformat(),
            "debut": debut.strftime("%H:%M:%S"),
            "fin": fin.strftime("%H:%M:%S"),
            "description": desc,
            "color": color,
            "technicien": tech_selected,
            "image_url": json.dumps(image_urls)
        }).execute()

        # =========================
        # PUSH NOTIFICATION
        # =========================
        send_push(
            desc,
            date.strftime("%d/%m/%Y"),
            debut.strftime("%H:%M"),
            fin.strftime("%H:%M"),
            tech_selected
        )

        # =========================
        # RESET PROPRE
        # =========================
        st.session_state.reset_sidebar = True
        st.session_state.upload_key += 1  # 🔥 reset uploader

        st.success("Activité ajoutée ✅")
        st.rerun()
# =========================
# TRI
# =========================
if not df.empty:
    df = df.sort_values(["date","debut"])

# =========================
# CALCUL HEURES
# =========================
def calc_heures(row):
    try:
        d = datetime.strptime(row["debut"], "%H:%M:%S")
        f = datetime.strptime(row["fin"], "%H:%M:%S")
        return (f - d).seconds / 3600
    except:
        return 0

# Calculer sur df
if not df.empty:
    df["heures"] = df.apply(calc_heures, axis=1)

# =========================
# 📋 POPUP ACTIVITÉ (UNIQUE)
# =========================
# =========================
# INIT
# =========================
if "zoom_image" not in st.session_state:
    st.session_state.zoom_image = None

if "show_zoom" not in st.session_state:
    st.session_state.show_zoom = False

# =========================
# 🖼️ POPUP ZOOM IMAGE
# =========================
@st.dialog("🖼️ Image en grand")
def popup_zoom_image():
    img = st.session_state.get("zoom_image")

    if img:
        st.image(img, use_container_width=True)

    if st.button("Fermer"):
        st.session_state.show_zoom = False
        st.session_state.zoom_image = None
        st.rerun()
# =========================
# 📋 POPUP ACTIVITÉ
# =========================
@st.dialog("📋 Activité")
def popup_activity(row):

    st.subheader("📄 Description")
    st.code(row["description"])

    st.write(f"📅 {format_date_fr(row['date'])}")
    st.write(f"⏰ {row['debut']} → {row['fin']}")
    st.write(f"👷 {row.get('technicien','Non défini')}")

    # =========================
    # 🖼️ IMAGES
    # =========================
    if "image_url" in row and row["image_url"]:
        try:
            images = json.loads(row["image_url"])
        except:
            images = [row["image_url"]]

        if not isinstance(images, list):
            images = [images]

        valid_images = [
            img for img in images
            if isinstance(img, str) and img.startswith("http")
        ]

        if valid_images:
            img_cols = st.columns(len(valid_images))

            for i, img in enumerate(valid_images):
                with img_cols[i]:
                    st.image(img, use_container_width=True)

                    # Bouton compact, icône seule
                    if st.button("🔍", key=f"zoom_cal_{row['id']}_{i}"):
                        st.session_state.zoom_image = img
                        st.session_state.show_zoom = True
                        st.rerun()
# =========================
# OUVERTURE POPUP ZOOM
# =========================
if st.session_state.get("show_zoom"):
    popup_zoom_image()
# =========================
# 📅 CALENDRIER
# =========================
if page == "📅 Calendrier":

    st.header("📅 Calendrier")

    if df.empty:
        st.info("Aucune activité")

    else:

        # =========================
        # 1️⃣ EVENTS
        # =========================
        events = []

        for _, row in df.iterrows():

            raw_title = str(row.get("description", "")).split("\n")[0]
            title = (raw_title[:37] + "...") if len(raw_title) > 40 else raw_title

            events.append({
                "id": str(row["id"]),
                "title": title,
                "start": f"{row['date']}T{row['debut']}",
                "end": f"{row['date']}T{row['fin']}",
                "color": row.get("color", "#00ff9c")
            })

        # =========================
        # 2️⃣ CALENDAR (FIX TIMEZONE)
        # =========================
        state = calendar(
            events=events,
            options={
                "locale": "fr",
                "firstDay": 1,
                "timeZone": "local",  # ✅ corrige le décalage

                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay"
                },
                "buttonText": {
                    "today": "Aujourd'hui",
                    "month": "Mois",
                    "week": "Semaine",
                    "day": "Jour"
                }
            },
            callbacks=["eventClick"]
        )

        # =========================
        # 3️⃣ CLICK EVENT → POPUP
        # =========================
        if state and state.get("eventClick"):

            event_id = state["eventClick"]["event"]["id"]

            filtered = df[df["id"].astype(str) == str(event_id)]

            if not filtered.empty:
                popup_activity(filtered.iloc[0])

# =========================
# LISTE
# =========================
if page == "📂 Liste":

    st.header("📂 Activités")

    # --- Barre de recherche ---
    col_search1, col_search2, col_search3 = st.columns([4, 1.2, 1.2])

    with col_search1:
        search_text = st.text_input("🔎 Recherche mot clé", value=st.session_state.get("search_text", ""))

    with col_search2:
        lancer = st.button("Chercher")

    with col_search3:
        reset = st.button("Reset")

    # --- Gestion des boutons ---
    if reset:
        st.session_state.search_text = ""
        search_text = ""
        lancer = True  # recharge la liste complète

    if lancer:
        st.session_state.search_text = search_text

    # --- Filtrage ---
    filtre = st.session_state.get("search_text", "")
    filtered_df = df.copy()

    if filtre:
        mots = filtre.split()
        for mot in mots:
            filtered_df = filtered_df[
                filtered_df["description"]
                .astype(str)
                .str.contains(mot, case=False, na=False)
            ]

    # --- Résultats ---
    if filtered_df.empty:
        st.info("Aucune activité trouvée")

    else:
        for _, row in filtered_df.iterrows():

            col1, col2, col3 = st.columns([6, 1, 1])

            # --- Colonne principale ---
            with col1:
                st.subheader("📄 Description")
                st.code(row["description"])

                st.write(f"📅 {format_date_fr(row['date'])}")
                st.write(f"⏰ {row['debut']} → {row['fin']}")
                st.write(f"👷 Technicien : {row.get('technicien', 'Non défini')}")

                # Bouton fermer
                if st.button("Fermer", key=f"close{row['id']}"):
                    st.rerun()

                # --- Affichage images ---
                if "image_url" in row and row["image_url"]:
                    try:
                        images = json.loads(row["image_url"])
                    except:
                        images = [row["image_url"]]

                    if not isinstance(images, list):
                        images = [images]

                    valid_images = [
                        img for img in images
                        if isinstance(img, str) and img.startswith("http")
                    ]

                    if valid_images:
                        img_cols = st.columns(len(valid_images))

                        for i, img in enumerate(valid_images):
                            with img_cols[i]:
                                st.image(img, use_container_width=True)

            # --- Bouton modifier ---
            with col2:
                if st.button("✏", key=f"edit{row['id']}"):

                    st.session_state["edit_id"] = row["id"]
                    st.session_state["edit_desc"] = row["description"]
                    st.session_state["edit_date"] = row["date"]
                    st.session_state["edit_debut"] = row["debut"]
                    st.session_state["edit_fin"] = row["fin"]
                    st.session_state["edit_images"] = row.get("image_url", "[]")
                    st.session_state["edit_technicien"] = row.get("technicien", "MAT")
                    st.session_state["edit_color"] = row.get("color", "#00ff9c")

                    st.stop()

            # --- Bouton supprimer ---
            with col3:
                if st.button("❌", key=f"del{row['id']}"):
                    supabase.table("agenda").delete().eq("id", row["id"]).execute()
                    st.stop()


if page == "📊 Statistiques":

    st.header("📊 Statistiques")

    if df.empty:
        st.info("Pas de données")

    else:

        # =========================
        # CHOIX TECHNICIEN
        # =========================
        techniciens = ["Tous"] + sorted(df["technicien"].dropna().unique())

        tech_selected = st.selectbox(
            "👷 Choisir technicien",
            techniciens
        )

        # =========================
        # FILTRE DATA
        # =========================
        df_filtered = df.copy()

        if tech_selected != "Tous":
            df_filtered = df[df["technicien"] == tech_selected]

        # =========================
        # METRICS
        # =========================
        col1, col2 = st.columns(2)

        with col1:
            st.metric("⏱ Temps total", f"{round(df_filtered['heures'].sum(),2)} h")

        with col2:
            st.metric("📅 Activités", len(df_filtered))

        # =========================
        # HEURES PAR MOIS
        # =========================
        df_filtered["mois"] = pd.to_datetime(df_filtered["date"]).dt.strftime("%Y-%m")

        stats = df_filtered.groupby("mois")["heures"].sum()

        st.subheader("Heures par mois")

        st.bar_chart(stats)

if st.session_state.get("show_zoom"):
    popup_zoom_image()

# =========================
# Plan Usine
# =========================
if page == "🏭 Plan Usine":

    st.header("🏭 Plan Usine")

    if df.empty:
        st.info("Pas de données")

    else:

st.set_page_config(layout="wide")
st.title("🏭 Plan Usine Interactif")

st.write("Clique sur une machine pour afficher les activités.")

# =========================
# POSITIONS DU PLAN (à ajuster)
# =========================
positions = {
    "101.A": (20, 20),
    "111.A": (120, 20),
    "102.A": (20, 120),
    "15.A": (120, 120),

    "117": (300, 20),
    "105": (400, 20),
    "105.A": (500, 20),
    "107": (300, 120),
    "106": (400, 120),
    "25": (500, 120),
    "104": (600, 120),

    "112": (300, 250),
    "108": (400, 250),
    "103": (500, 250),
    "109": (600, 250),
    "123": (300, 350),
    "113": (400, 350),
    "110": (500, 350),
    "121": (600, 350),
    "123.A": (300, 450),
    "114": (400, 450),
    "119": (500, 450),
    "115": (600, 450),

    "101": (300, 580),
    "21": (400, 580),
    "120": (500, 580),
    "116": (600, 580),
    "23": (700, 580),
    "118": (800, 580),

    "24": (900, 250),
    "26": (900, 350),
    "22": (900, 450),
    "122": (900, 550),
    "27": (900, 650),
}

# =========================
# ÉTATS DES MACHINES
# =========================
status = {machine: "Auto" for machine in positions}

colors = {
    "Auto": "#2ecc71",
    "Arrêt": "#7f8c8d"
}

# =========================
# ACTIVITÉS (exemple)
# =========================
activities = {
    machine: [f"Activité exemple pour {machine}"]
    for machine in positions
}

# =========================
# AFFICHAGE DU PLAN
# =========================
html = """
<div style='position:relative;width:1200px;height:800px;
            background:#f0f0f0;border:2px solid #444;'>
"""

for machine, (x, y) in positions.items():
    color = colors[status[machine]]
    html += f"""
    <button onclick="window.location.href='?machine={machine}'"
        style="
            position:absolute;
            left:{x}px;
            top:{y}px;
            width:70px;
            height:70px;
            background:{color};
            border:none;
            border-radius:6px;
            color:white;
            font-weight:bold;
            cursor:pointer;
        ">
        {machine}
    </button>
    """

html += "</div>"

st.markdown(html, unsafe_allow_html=True)

machine = st.query_params.get("machine", None)

if machine:
    st.subheader(f"📋 Activités pour {machine}")
    for act in activities[machine]:
        st.write(f"• {act}")
