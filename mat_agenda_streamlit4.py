import streamlit as st
import pandas as pd
import json
from datetime import datetime
from streamlit_calendar import calendar
from supabase import create_client

# =========================
# SUPABASE
# =========================
url = "https://quamffmaxqhhtyxworou.supabase.co"
key = "sb_publishable_zKt7ObrIa8kkHXjlvhk4tw_SUetSTZG"
supabase = create_client(url, key)

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

# =========================
# RECHERCHE
# =========================
search = st.sidebar.text_input("🔎 Recherche mot clé")
search_date = st.sidebar.date_input("📅 Recherche par date")

filtered_df = df.copy()

if search:
    filtered_df = filtered_df[
        filtered_df["description"].str.contains(search, case=False, na=False)
    ]

if search_date:
    filtered_df = filtered_df[
        filtered_df["date"] == search_date.strftime("%Y-%m-%d")
    ]

# =========================
# MODIFICATION ACTIVITE
# =========================
if "edit_id" in st.session_state:

    st.subheader("✏ Modifier activité")

    new_date = st.date_input(
        "Date",
        value=pd.to_datetime(st.session_state["edit_date"])
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
        col1, col2 = st.columns([5,1])
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
        if new_uploads:
            for img in new_uploads:
                file_name = f"{int(datetime.now().timestamp()*1000)}_{img.name}"
                supabase.storage.from_("agenda-images").upload(file_name, img.getvalue())
                url = supabase.storage.from_("agenda-images").get_public_url(file_name)
                new_images_list.append(url)

        # Mise à jour Supabase
        supabase.table("agenda").update({
            "date": new_date.isoformat(),
            "debut": new_debut,
            "fin": new_fin,
            "description": new_desc,
            "image_url": json.dumps(new_images_list)
        }).eq("id", st.session_state["edit_id"]).execute()

        del st.session_state["edit_id"]
        st.success("Activité modifiée")
        st.experimental_rerun()

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
date = st.sidebar.date_input("Date")
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
            try:
                file_name = f"{int(datetime.now().timestamp()*1000)}_{image.name}"
                supabase.storage.from_("agenda-images").upload(file_name, image.getvalue())
                url = supabase.storage.from_("agenda-images").get_public_url(file_name)
                image_urls.append(url)
            except Exception as e:
                st.error(f"Erreur upload {image.name}: {e}")

    supabase.table("agenda").insert({
        "date": date.isoformat(),
        "debut": debut.strftime("%H:%M:%S"),
        "fin": fin.strftime("%H:%M:%S"),
        "description": desc,
        "color": color,
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
    if not df.empty:
        events = []
        for _, row in df.iterrows():
            events.append({
                "title": row["description"].split("\n")[0][:40],
                "start": row["date"] + "T" + row["debut"],
                "end": row["date"] + "T" + row["fin"],
                "color": row["color"]
            })
        calendar(events=events)

        # afficher activités du jour
        st.subheader("📅 Voir les activités d'une date")
        selected_date = st.date_input("Choisir une date")
        day_activities = df[df["date"] == selected_date.strftime("%Y-%m-%d")]

        if not day_activities.empty:
            for _, row in day_activities.iterrows():
                st.markdown(f"### {row['debut']} → {row['fin']}\n\n{row['description']}")

                # affichage multi-images sur la même ligne
                images = row.get("image_url")
                if images:
                    if isinstance(images,str):
                        try:
                            images = json.loads(images)
                        except:
                            images = [images]
                    if not isinstance(images,list):
                        images = [images]
                    if images:
                        cols = st.columns(len(images))
                        for i, img in enumerate(images):
                            if img and str(img).startswith("http"):
                                cols[i].image(img, use_container_width=True)
        else:
            st.info("Aucune activité pour cette date")
    else:
        st.info("Aucune activité")

# =========================
# LISTE
# =========================
if page == "📂 Liste":
    st.header("📂 Activités")
    if filtered_df.empty:
        st.info("Aucune activité")
    else:
for _, row in filtered_df.iterrows():
    col1, col2, col3 = st.columns([6,1,1])

    # Colonne 1 : affichage description + images
    with col1:
        st.markdown(f"""
### {row['description']}

📅 {row['date']}

⏰ {row['debut']} → {row['fin']}

⏱ Durée : {round(row.get('heures', 0),2)} h
""")
        # affichage images sur la même ligne
        if "image_url" in row and row["image_url"]:
            try:
                images = json.loads(row["image_url"])
            except:
                images = [row["image_url"]]

            if images:
                cols = st.columns(len(images))
                for i, img in enumerate(images):
                    if img and str(img).startswith("http"):
                        cols[i].image(img, use_container_width=True)

    # Colonne 2 : modifier
    with col2:
        if st.button("✏", key=f"edit{row['id']}"):
            st.session_state["edit_id"] = row["id"]
            st.session_state["edit_desc"] = row["description"]
            st.session_state["edit_date"] = row["date"]
            st.session_state["edit_debut"] = row["debut"]
            st.session_state["edit_fin"] = row["fin"]
            st.session_state["edit_images"] = row.get("image_url", "[]")
            st.experimental_rerun()

    # Colonne 3 : supprimer
    with col3:
        if st.button("❌", key=f"del{row['id']}"):
            supabase.table("agenda").delete().eq("id", row["id"]).execute()
            st.experimental_rerun()

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
