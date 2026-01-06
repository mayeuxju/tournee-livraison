import streamlit as st
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import plotly.express as px

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Gestionnaire de Tournées Pro",
    page_icon="🚚",
    layout="wide"
)

# --- STYLE CSS ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .latency-line {
        border-left: 4px solid #28a745;
        margin: 10px 0 10px 30px;
        padding: 10px 0 10px 20px;
        color: #28a745;
        font-weight: bold;
    }
    .address-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        border-left: 5px solid #1f77b4;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION API ---
if "google" in st.secrets:
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    except Exception as e:
        st.error(f"Erreur API : {e}")
        st.stop()
else:
    st.error("⚠️ Clé API manquante dans les Secrets Streamlit.")
    st.stop()

# --- FONCTION DE CALCUL ---
def get_route_details(addresses, mode_transport, avoid_tolls):
    results = []
    total_dist = 0
    total_time = 0
    
    # On ajuste la vitesse si c'est un poids lourd (environ 20% plus lent)
    vitesse_factor = 0.8 if mode_transport == "Poids Lourd" else 1.0
    
    for i in range(len(addresses) - 1):
        try:
            directions = gmaps.directions(
                addresses[i],
                addresses[i+1],
                mode="driving",
                departure_time=datetime.now(),
                avoid="tolls" if avoid_tolls else None
            )
            
            if directions:
                leg = directions[0]['legs'][0]
                dist_km = leg['distance']['value'] / 1000
                # On applique le facteur de vitesse sur la durée
                duration_sec = (leg['duration_in_traffic']['value'] / vitesse_factor)
                
                results.append({
                    "depart": addresses[i],
                    "arrivee": addresses[i+1],
                    "distance": f"{dist_km:.1f} km",
                    "temps": str(timedelta(seconds=int(duration_sec))),
                    "lat": leg['end_location']['lat'],
                    "lng": leg['end_location']['lng'],
                    "time_val": duration_sec / 60
                })
                total_dist += dist_km
                total_time += duration_sec
        except Exception as e:
            st.warning(f"Impossible de calculer le trajet entre {addresses[i]} et {addresses[i+1]}")
            
    return results, total_dist, total_time

# --- BARRE LATÉRALE ---
st.sidebar.header("⚙️ Paramètres")
uploaded_file = st.sidebar.file_uploader("Charger le fichier (Excel ou CSV)", type=["xlsx", "csv"])
mode = st.sidebar.selectbox("Type de véhicule", ["Voiture", "Poids Lourd"])
tolls = st.sidebar.checkbox("Éviter les péages")

# --- CORPS PRINCIPAL ---
st.title("🚚 Optimisateur de Tournée")

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        if "Adresse" not in df.columns:
            st.error("Le fichier doit contenir une colonne nommée 'Adresse'")
        else:
            adresses = df["Adresse"].tolist()
            
            if st.button("🚀 Générer la feuille de route"):
                with st.spinner('Calcul des trajets en cours avec Google Maps...'):
                    itinerary, t_dist, t_time = get_route_details(adresses, mode, tolls)
                
                tab1, tab2, tab3 = st.tabs(["📋 Feuille de Route", "🗺️ Carte", "📊 Statistiques"])
                
                with tab1:
                    st.subheader("Itinéraire Chronologique")
                    # Premier point
                    st.markdown(f'<div class="address-card">📍 **Départ :** {adresses[0]}</div>', unsafe_allow_html=True)
                    
                    for step in itinerary:
                        # Ligne verte de trajet
                        st.markdown(f'<div class="latency-line">🕒 {step["temps"]} ({step["distance"]})</div>', unsafe_allow_html=True)
                        # Point d'arrivée
                        st.markdown(f'<div class="address-card">📍 **Client :** {step["arrivee"]}</div>', unsafe_allow_html=True)
                
                with tab2:
                    m = folium.Map(location=[itinerary[0]['lat'], itinerary[0]['lng']], zoom_start=10)
                    for step in itinerary:
                        folium.Marker([step['lat'], step['lng']], popup=step['arrivee']).add_to(m)
                    folium_static(m)
                
                with tab3:
                    col1, col2 = st.columns(2)
                    col1.metric("Distance Totale", f"{t_dist:.1f} km")
                    col2.metric("Temps Total Est.", str(timedelta(seconds=int(t_time))))
                    
                    df_plot = pd.DataFrame(itinerary)
                    fig = px.bar(df_plot, x="arrivee", y="time_val", title="Temps de trajet (minutes)")
                    st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
else:
    st.info("Veuillez charger un fichier pour commencer.")
