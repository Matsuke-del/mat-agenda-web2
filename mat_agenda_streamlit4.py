import streamlit as st
import pandas as pd
import json
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
# Ajout tech
# =========================
# Liste des techniciens
techniciens = ["Alice", "Bob", "Charlie", "David"]

# Choix du technicien pour l'activité
tech_selected = st.sidebar.selectbox("🛠 Technicien", techniciens)

# Ensuite la date, début, fin, description, couleur, images...
date = st.sidebar.date_input("📅 Date", format="DD/MM/YYYY")
debut = st.sidebar.time_input("Début")
fin = st.sidebar.time_input("Fin")
desc = st.sidebar.text_area("Description")
color = st.sidebar.color_picker("Couleur", "#00ff9c")

images = st.sidebar.file_uploader(
    "Images activité (plusieurs possibles)",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

# =========================
# MODIFICATION ACTIVITE
# =========================
if "edit_id" in st.session_state:

    st.subheader("✏ Modifier activité")

    new_date = st.date_input(
        "📅 Date",
        value=pd.to_datetime(st.session_state["edit_date"]),
        format="DD/MM/YYYY"
    )
    new_debut = st.text_input("Début", st.session_state["edit_debut"])
    new_fin = st.text_input("Fin", st.session_state["edit_fin"])
    new_desc = st.text_area("Description", value=st.session_state["edit_desc"])

    # Images existantes
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

    # Ajout nouvelles images
    new_uploads = st.file_uploader(
        "Ajouter nouvelles images",
        type=["png","jpg","jpeg"],
        accept_multiple_files=True
    )

    if st.button("Enregistrer modification"):
        # Upload nouvelles images
        if new_uploads:
            for img in new_uploads:
                file_name = f"{int(datetime.now().timestamp()*1000)}_{img.name}"
                try:
                    supabase.storage.from_("agenda-images").upload(file_name, img.getvalue())
                    url = supabase.storage.from_("agenda-images").get_public_url(file_name)
                    new_images_list.append(url)
                except Exception as e:
                    st.error(f"Erreur upload {img.name}: {e}")

        # Mise à jour Supabase
        supabase.table("agenda").update({
            "date": new_date.isoformat(),
            "debut": new_debut,
            "fin": new_fin,
            "description": new_desc,
            "image_url": json.dumps(new_images_list)
        }).eq("id", st.session_state["edit_id"]).execute()

        # Nettoyage session_state
        st.session_state.pop("edit_id", None)
        st.session_state.pop("edit_desc", None)
        st.session_state.pop("edit_date", None)
        st.session_state.pop("edit_debut", None)
        st.session_state.pop("edit_fin", None)
        st.session_state.pop("edit_images", None)

        st.success("Activité modifiée ! Veuillez rafraîchir la page pour voir les changements.")

# =========================
# NAVIGATION
# =========================
page = st.sidebar.radio(
    "Navigation",
    ["📅 Calendrier", "📂 Liste", "📊 Statistiques"]
)

# =========================
# AJOUT ACTIVITE
# =========================
st.sidebar.header("➕ Ajouter activité")
date = st.sidebar.date_input(
    "📅 Date",
    format="DD/MM/YYYY",
    key="sidebar_date"
)
debut = st.sidebar.time_input("Début")
fin = st.sidebar.time_input("Fin")
desc = st.sidebar.text_area("Description")
color = st.sidebar.color_picker("Couleur", "#00ff9c")

images = st.sidebar.file_uploader(
    "Images activité (plusieurs possibles)",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

image_urls = []
if images:
    for image in images:
        try:
            file_name = f"{int(datetime.now().timestamp()*1000)}_{image.name}"
            supabase.storage.from_("agenda-images").upload(file_name, image.getvalue())
            url = supabase.storage.from_("agenda-images").get_public_url(file_name)
            image_urls.append(url)
        except Exception as e:
            st.error(f"Erreur upload {image.name}: {e}")

if st.sidebar.button("Ajouter activité"):
    image_urls = []
    if images:
        for image in images:
            file_name = f"{int(datetime.now().timestamp()*1000)}_{image.name}"
            supabase.storage.from_("agenda-images").upload(file_name, image.getvalue())
            url = supabase.storage.from_("agenda-images").get_public_url(file_name)
            image_urls.append(url)
        
    supabase.table("agenda").insert({
        "date": date.isoformat(),
        "debut": debut.strftime("%H:%M:%S"),
        "fin": fin.strftime("%H:%M:%S"),
        "description": desc,
        "color": color,
        "technicien": tech_selected,   # <-- ajout du technicien
        "image_url": json.dumps(image_urls)
    }).execute()

    st.success("Activité ajoutée")
    st.experimental_rerun()

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

# Calculer sur filtered_df après filtrage
if not filtered_df.empty:
    filtered_df["heures"] = filtered_df.apply(calc_heures, axis=1)

# =========================
# CALENDRIER
# =========================
if page == "📅 Calendrier":
    st.header("📅 Calendrier")

    if df.empty:
        st.info("Aucune activité")
    else:

        # -----------------------------
        # 1) Construction des événements
        # -----------------------------
        events = []

        for _, row in df.iterrows():

            raw_title = row["description"].split("\n")[0]
            title = (raw_title[:37] + "...") if len(raw_title) > 40 else raw_title

            events.append({
                "id": row["id"],
                "title": title,
                "start": row["date"] + "T" + row["debut"],
                "end": row["date"] + "T" + row["fin"],
                "color": row["color"]
            })

        # -----------------------------
        # 2) Affichage du calendrier
        # -----------------------------
        state = calendar(
            events=events,
            options={
                "locale": "fr",
                "firstDay": 1,
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

        # -----------------------------
        # 3) Popup activité
        # -----------------------------
        @st.dialog("📋 Activité")
        def popup_activity(row):

            st.markdown(f"""
### {row['description']}

📅 {format_date_fr(row['date'])}

⏰ {row['debut']} → {row['fin']}
""")

            if st.button("Fermer"):
                st.rerun()

        # -----------------------------
        # 4) Détection clic activité
        # -----------------------------
        if state and state.get("eventClick"):

            event_id = state["eventClick"]["event"]["id"]

    # convertir en string pour éviter conflit type
            filtered = df[df["id"].astype(str) == str(event_id)]

            if not filtered.empty:
                row = filtered.iloc[0]
                popup_activity(row)

        # -----------------------------
        # 5) Activités du jour
        # -----------------------------
        st.subheader("📅 Voir les activités d'une date")

        selected_date = st.date_input("Choisir une date")
        selected_str = selected_date.strftime("%Y-%m-%d")

        day_activities = df[df["date"] == selected_str]

        if day_activities.empty:
            st.info("Aucune activité pour cette date")

        else:
            for _, row in day_activities.iterrows():

                st.markdown(f"""
### 📅 {format_date_fr(row['date'])}

⏰ {row['debut']} → {row['fin']}

**Technicien :** {row.get('technicien', 'Non défini')}

{row['description']}
""")

                # -----------------------------
                # 6) Gestion images
                # -----------------------------
                images = row.get("image_url")

                if images:

                    if isinstance(images, str):
                        try:
                            images = json.loads(images)
                        except:
                            images = [images]

                    if not isinstance(images, list):
                        images = [images]

                    valid_images = [
                        img for img in images
                        if isinstance(img, str) and img.startswith("http")
                    ]

                    if valid_images:
                        cols = st.columns(len(valid_images))

                        for i, img in enumerate(valid_images):
                            cols[i].image(img, use_container_width=True)
# =========================
# LISTE
# =========================
if page == "📂 Liste":

    st.header("📂 Activités")

    # --- Recherche ---
    col_search1, col_search2, col_search3 = st.columns([3, 3, 1])

    with col_search1:
        search_text = st.text_input("🔎 Recherche mot clé")

    with col_search2:
        search_date = st.date_input(
            "📅 Recherche par date",
            format="DD/MM/YYYY",
            key="search_date"
         )


    with col_search3:
        reset = st.button("❌")

    # Reset recherche
    if reset:
        search_text = ""
        search_date = None

    filtered_df = df.copy()

    # --- Filtre mot clé ---
    if search_text:
        mots = search_text.split()
        for mot in mots:
            filtered_df = filtered_df[
                filtered_df["description"]
                .astype(str)
                .str.contains(mot, case=False, na=False)
            ]

    # --- Filtre date ---
    if search_date:
        filtered_df = filtered_df[
            filtered_df["date"] == search_date.strftime("%Y-%m-%d")
        ]

    # --- Résultats ---
    if filtered_df.empty:
        st.info("Aucune activité trouvée")

    else:
        for _, row in filtered_df.iterrows():

            col1, col2, col3 = st.columns([6, 1, 1])

            # --- Colonne principale ---
            with col1:
                st.markdown(f"""
### {row['description']}

📅 {format_date_fr(row['date'])}

⏰ {row['debut']} → {row['fin']}

**Technicien :** {row.get('technicien', 'Non défini')}
""")

                # Bouton fermer (si tu veux le garder ici)
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
                            img_cols[i].image(img, use_container_width=True)

            # --- Bouton modifier ---
            with col2:
                if st.button("✏", key=f"edit{row['id']}"):
                    st.session_state["edit_id"] = row["id"]
                    st.session_state["edit_desc"] = row["description"]
                    st.session_state["edit_date"] = row["date"]
                    st.session_state["edit_debut"] = row["debut"]
                    st.session_state["edit_fin"] = row["fin"]
                    st.session_state["edit_images"] = row.get("image_url", "[]")
                    st.stop()

            # --- Bouton supprimer ---
            with col3:
                if st.button("❌", key=f"del{row['id']}"):
                    supabase.table("agenda").delete().eq("id", row["id"]).execute()
                    st.stop()

# =========================
# STATISTIQUES
# =========================
if page == "📊 Statistiques":
    st.header("📊 Statistiques")
    if df.empty:
        st.info("Pas de données")
    else:
        col1,col2 = st.columns(2)
        with col1:
            st.metric("⏱ Temps total", f"{round(df['heures'].sum(),2)} h")
        with col2:
            st.metric("📅 Activités", len(df))
        df["mois"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        stats = df.groupby("mois")["heures"].sum()
        st.subheader("Heures par mois")
        st.bar_chart(stats)
