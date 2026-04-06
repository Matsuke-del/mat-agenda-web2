import streamlit as st
import pandas as pd
from datetime import datetime
import os
from streamlit_calendar import calendar
from supabase import create_client

url = "https://quamffmaxqhhtyxworou.supabase.co"
key = "sb_publishable_zKt7ObrIa8kkHXjlvhk4tw_SUetSTZG"
supabase = create_client(url, key)


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
# NAVIGATION
# =========================

page=st.sidebar.radio(
"Navigation",
["📅 Calendrier","📂 Liste","📊 Statistiques"]
)

# =========================
# AJOUT ACTIVITE
# =========================

if st.sidebar.button("Ajouter activité"):

    try:

        supabase.table("agenda").insert({

            "date": str(date),
            "debut": debut.strftime("%H:%M:%S"),
            "fin": fin.strftime("%H:%M:%S"),
            "description": desc,
            "color": color

        }).execute()

        st.success("Activité ajoutée")

        st.rerun()

    except Exception as e:

        st.error(e)

# =========================
# TRI
# =========================

if not df.empty:
    df=df.sort_values(["date","debut"])

# =========================
# CALCUL HEURES
# =========================

def calc_heures(row):

    try:
        d=datetime.strptime(row["debut"],"%H:%M:%S")
        f=datetime.strptime(row["fin"],"%H:%M:%S")

        return (f-d).seconds/3600
    except:
        return 0

if not df.empty:
    df["heures"]=df.apply(calc_heures,axis=1)

# =========================
# RECHERCHE
# =========================

search=st.sidebar.text_input("🔎 Recherche")

if search!="" and not df.empty:
    df=df[df["description"].str.contains(search,case=False)]

# =========================
# CALENDRIER
# =========================

if page=="📅 Calendrier":

    st.header("📅 Calendrier")

    if not df.empty:

        events=[]

        for _,row in df.iterrows():

            events.append({
            "title":row["description"].split("\n")[0][:40],
            "start":row["date"]+"T"+row["debut"],
            "end":row["date"]+"T"+row["fin"],
            "color":row["color"]
            })

        calendar(events=events)

        # =========================
        # ACTIVITES PAR DATE
        # =========================

        st.subheader("📅 Voir les activités d'une date")

        selected_date = st.date_input("Choisir une date")

        day_activities = df[df["date"] == selected_date.strftime("%Y-%m-%d")]

        if not day_activities.empty:

            for _,row in day_activities.iterrows():

                st.markdown(f"""
### {row['debut']} → {row['fin']}

{row['description']}
""")

        else:

            st.info("Aucune activité pour cette date")

    else:

        st.info("Aucune activité")

# =========================
# LISTE
# =========================

if page=="📂 Liste":

    st.header("📂 Activités")

    if df.empty:
        st.info("Aucune activité")

    else:

        for _,row in df.iterrows():

            col1,col2=st.columns([6,1])

            with col1:

                st.markdown(f"""
### {row['description']}

📅 {row['date']}

⏰ {row['debut']} → {row['fin']}

⏱ {round(row['heures'],2)} h
""")

            with col2:

                if st.button("❌", key=row["id"]):

                    supabase.table("agenda").delete().eq("id", row["id"]).execute()

                    st.rerun()
# =========================
# STATISTIQUES
# =========================

if page=="📊 Statistiques":

    st.header("📊 Statistiques")

    if df.empty:

        st.info("Pas de données")

    else:

        col1,col2=st.columns(2)

        with col1:
            st.metric("⏱ Temps total",f"{round(df['heures'].sum(),2)} h")

        with col2:
            st.metric("📅 Activités",len(df))

        df["mois"]=pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

        stats=df.groupby("mois")["heures"].sum()

        st.subheader("Heures par mois")

        st.bar_chart(stats)
