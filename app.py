import streamlit as st
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import plotly.express as px
import io

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Gestionnaire de Tournées Pro",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE CSS (Pour mobile et lignes de trajet) ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border-radius: 5px 5px 0px 0px;
        padding: 10px 20px;
    }
    .latency-line {
        border-left: 4px solid #28a745;
        margin-left: 20px;
        padding-left: 20px;
        padding-top: 5px;
        padding-bottom: 5px;
        color: #28a745;
        font-weight: bold;
        font-size: 0.9em;
    }
    .address-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        border-left: 5px solid #1f77b4;
    }
    @media (max-width: 600px) {
        .stMetric { font-size: 0.8rem; }
    }
    </style>
    """, unsafe_allow_index=True)

# --- INITIALISATION API GOOGLE ---
if "google" in st.secrets:
    try:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    except Exception as e:
        st.error(f"Erreur d'initialisation API : {e}")
        st.stop()
else:
    st.error("⚠️ Clé API non trouvée dans les Secrets Streamlit !")
    st.stop()

# --- GESTION DE L'HISTORIQUE ---
if 'history' not in st.session_state:
    st.session_state.history = []

# --- LOGIQUE DE CALCUL ---
def get_route_details(addresses, mode_transport, avoid_tolls):
    results = []
    total_dist = 0
    total_time = 0
    
    # Paramètres selon le véhicule
    vitesse_factor = 0.85 if mode_transport == "Poids Lourd" else 1.0
    
    for i in range(len(addresses) - 1):
        try:
            now = datetime.now()
            # Appel API Directions avec trafic en temps réel
            directions = gmaps.directions(
                addresses[i],
                addresses[i+1],
                mode="driving",
                departure_time=now,
                avoid="tolls" if avoid_tolls else None
            )
            
            if directions:
                leg = directions[0]['legs'][0]
                dist_val = leg['distance']['value'] / 1000 # km
                # On utilise duration_in_traffic si disponible
                time_val = leg.get('duration_in_traffic', leg['duration'])['value'] / vitesse_factor
                
                results.append({
                    "start": addresses[i],
                    "end": addresses[i+1],
                    "dist_str": leg['distance']['text'],
                    "time_str": str(timedelta(seconds=int(time_val))),
                    "dist_val": dist_val,
                    "time_val": time_val / 60, # minutes
                    "end_coords": (leg['end_location']['lat'], leg['end_location']['lng'])
                })
                total_dist += dist_val
                total_time += time_val
        except Exception as e:
            st.warning(f"Impossible de calculer le trajet entre {addresses[i]} et {addresses[i+1]}")
            
    return results, total_dist, total_time

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2830/2830305.png", width=100)
    st.title("Configuration")
    
    vehicule = st.selectbox("Type de véhicule", ["Voiture", "Poids Lourd"])
    peages = st.toggle("Éviter les péages", value=False)
    
    st.divider()
    uploaded_file = st.file_uploader("📂 Charger adresses (Excel ou CSV)", type=['xlsx', 'csv'])
    st.info("Le fichier doit contenir une colonne nommée 'Adresse'")

# --- CORPS DE L'APPLICATION ---
if uploaded_file:
    # Lecture des données
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        if 'Adresse' not in df.columns:
            st.error("Colonne 'Adresse' manquante !")
            st.stop()
            
        addresses = df['Adresse'].dropna().tolist()
        
        if len(addresses) < 2:
            st.warning("Il faut au moins 2 adresses pour calculer une tournée.")
        else:
            # Calcul de l'itinéraire
            with st.spinner('Calcul des temps de trajet avec Google Maps...'):
                itinerary, t_dist, t_time = get_route_details(addresses, vehicule, peages)

            # --- AFFICHAGE DES ONGLETS ---
            tab1, tab2, tab3 = st.tabs(["📋 Feuille de Route", "🗺️ Carte Interactive", "📊 Statistiques & Export"])

            with tab1:
                st.subheader("Planning de livraison")
                
                # Point de départ
                st.markdown(f'<div class="address-card">🏠 <b>DÉPART :</b> {addresses[0]}</div>', unsafe_allow_index=True)
                
                for step in itinerary:
                    # Ligne de trajet (Ligne verte)
                    st.markdown(f'''
                        <div class="latency-line">
                            ⏱️ {step["time_str"]} | 🛣️ {step["dist_str"]}
                        </div>
                    ''', unsafe_allow_index=True)
                    
                    # Point suivant
                    st.markdown(f'<div class="address-card">📍 <b>CLIENT :</b> {step["end"]}</div>', unsafe_allow_index=True)

            with tab2:
                st.subheader("Visualisation du parcours")
                if itinerary:
                    m = folium.Map(location=[itinerary[0]['end_coords'][0], itinerary[0]['end_coords'][1]], zoom_start=10)
                    
                    # Ajouter les points sur la carte
                    folium.Marker([itinerary[0]['end_coords'][0], itinerary[0]['end_coords'][1]], 
                                  tooltip="Départ", icon=folium.Icon(color='red')).add_to(m)
                                  
                    for step in itinerary:
                        folium.Marker([step['end_coords'][0], step['end_coords'][1]], 
                                      tooltip=step['end']).add_to(m)
                    
                    folium_static(m)

            with tab3:
                # Métriques
                col1, col2 = st.columns(2)
                col1.metric("Distance Totale", f"{t_dist:.1f} km")
                col2.metric("Temps de Conduite Est.", str(timedelta(seconds=int(t_time))))
                
                # Graphique des temps entre clients
                df_plot = pd.DataFrame(itinerary)
                fig = px.bar(df_plot, x="end", y="time_val", title="Temps de trajet par étape (min)", labels={'time_val':'Minutes', 'end':'Client'})
                st.plotly_chart(fig, use_container_width=True)
                
                # Export CSV
                csv = df_plot[['start', 'end', 'dist_str', 'time_str']].to_csv(index=False).encode('utf-8')
                st.download_button("📥 Télécharger la feuille de route (CSV)", csv, "tournee.csv", "text/csv")

    except Exception as e:
        st.error(f"Erreur lors de l'analyse du fichier : {e}")
else:
    # Page d'accueil si aucun fichier
    st.title("Bienvenue dans votre outil de tournée")
    st.write("Veuillez charger un fichier Excel ou CSV contenant vos adresses dans la barre latérale pour commencer.")
    st.image("https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&q=80&w=1000", use_container_width=True)
