import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
from streamlit_calendar import calendar

# ========================
# CONFIG SUPABASE
# ========================

url = "TON_URL_SUPABASE"
key = "TA_CLE_API"

supabase = create_client(url, key)

st.set_page_config(layout="wide")

st.title("🧠 MAT AGENDA CLOUD")

# ========================
# STYLE CYBER
# ========================

st.markdown("""
<style>
body {background:#0b0f14;color:#00ff9c;}
h1,h2 {color:#00ffee;}
</style>
""",unsafe_allow_html=True)

# ========================
# LECTURE BASE
# ========================

def lire_data():

    response = supabase.table("agenda").select("*").execute()

    data=response.data

    return pd.DataFrame(data)

df=lire_data()

# ========================
# AJOUT ACTIVITE
# ========================

st.header("➕ Ajouter activité")

col1,col2,col3=st.columns(3)

with col1:
    date=st.date_input("Date")

with col2:
    debut=st.time_input("Début")

with col3:
    fin=st.time_input("Fin")

desc=st.text_area("Description")

if st.button("Ajouter"):

    supabase.table("agenda").insert({
    "date":str(date),
    "debut":str(debut),
    "fin":str(fin),
    "description":desc
    }).execute()

    st.success("Activité ajoutée")

# ========================
# RECHERCHE
# ========================

st.header("🔍 Recherche")

search=st.text_input("mot clé")

if search!="":
    df=df[df["description"].str.contains(search,case=False)]

# ========================
# CALCUL HEURES
# ========================

def calc_heures(row):

    d=datetime.strptime(row["debut"],"%H:%M:%S")

    f=datetime.strptime(row["fin"],"%H:%M:%S")

    return (f-d).seconds/3600

if not df.empty:

    df["heures"]=df.apply(calc_heures,axis=1)

# ========================
# LISTE ACTIVITES
# ========================

st.header("📂 Activités")

for i,row in df.iterrows():

    col1,col2=st.columns([6,1])

    with col1:

        st.markdown(f"""
**{row['date']} | {row['debut']} - {row['fin']}**

{row['description']}
""")

    with col2:

        if st.button("❌",key=row["id"]):

            supabase.table("agenda").delete().eq("id",row["id"]).execute()

            st.experimental_rerun()

# ========================
# CALENDRIER
# ========================

st.header("📅 Calendrier")

if not df.empty:

    events=[]

    for _,row in df.iterrows():

        events.append({
        "title":row["description"],
        "start":row["date"]
        })

    calendar(events=events)

# ========================
# STATS
# ========================

if not df.empty:

    st.header("📊 Statistiques")

    df["mois"]=pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

    stats=df.groupby("mois")["heures"].sum()

    st.bar_chart(stats)