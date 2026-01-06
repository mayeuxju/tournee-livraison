import streamlit as st
import pandas as pd
import googlemaps
from datetime import datetime, timedelta
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go

# Configuration de la page
st.set_page_config(
    page_title="Optimisation Tournées - Suisse",
    page_icon="🚚",
    layout="wide"
)

# Initialisation de Google Maps
@st.cache_resource
def init_gmaps():
    try:
        api_key = st.secrets["google"]["api_key"]
        return googlemaps.Client(key=api_key)
    except Exception as e:
        st.error(f"❌ Erreur de connexion Google Maps : {str(e)}")
        return None

gmaps = init_gmaps()

# Initialisation de la session
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []

# Titre
st.title("🚚 Optimisation de Tournées - Suisse")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📍 Ajouter une livraison")
    
    with st.form("formulaire_livraison"):
        nom_client = st.text_input("👤 Nom du client")
        adresse = st.text_area("📍 Adresse complète", 
                               help="Ex: Rue du Lac 15, 1005 Lausanne")
        
        col1, col2 = st.columns(2)
        with col1:
            heure_debut = st.time_input("🕐 Heure début", 
                                        value=datetime.strptime("09:00", "%H:%M").time())
        with col2:
            heure_fin = st.time_input("🕐 Heure fin", 
                                      value=datetime.strptime("17:00", "%H:%M").time())
        
        duree_livraison = st.number_input("⏱️ Durée livraison (min)", 
                                         min_value=5, max_value=120, value=15)
        
        submitted = st.form_submit_button("➕ Ajouter", use_container_width=True)
        
        if submitted and nom_client and adresse:
            if gmaps:
                # Géocodage de l'adresse
                try:
                    geocode_result = gmaps.geocode(adresse + ", Suisse")
                    if geocode_result:
                        location = geocode_result[0]['geometry']['location']
                        
                        livraison = {
                            'id': len(st.session_state.livraisons) + 1,
                            'client': nom_client,
                            'adresse': adresse,
                            'lat': location['lat'],
                            'lng': location['lng'],
                            'heure_debut': heure_debut.strftime("%H:%M"),
                            'heure_fin': heure_fin.strftime("%H:%M"),
                            'duree': duree_livraison,
                            'statut': '⏳ En attente'
                        }
                        
                        st.session_state.livraisons.append(livraison)
                        st.success(f"✅ {nom_client} ajouté !")
                        st.rerun()
                    else:
                        st.error("❌ Adresse introuvable")
                except Exception as e:
                    st.error(f"❌ Erreur : {str(e)}")
            else:
                st.error("❌ Google Maps non disponible")

    st.markdown("---")
    
    # Statistiques
    st.header("📊 Statistiques")
    if st.session_state.livraisons:
        st.metric("Total livraisons", len(st.session_state.livraisons))
        
        # Durée totale estimée
        duree_totale = sum(l['duree'] for l in st.session_state.livraisons)
        st.metric("Temps total", f"{duree_totale} min")
    else:
        st.info("Aucune livraison ajoutée")
    
    # Bouton pour tout effacer
    if st.session_state.livraisons:
        if st.button("🗑️ Tout effacer", use_container_width=True):
            st.session_state.livraisons = []
            st.rerun()

# Zone principale
if not st.session_state.livraisons:
    st.info("👈 Ajoutez des livraisons dans le menu de gauche pour commencer")
else:
    # Onglets
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Liste", "🗺️ Carte", "📊 Analyse", "📥 Export"])
    
    # ============================================================
    # TAB 1 : LISTE DES LIVRAISONS
    # ============================================================
    with tab1:
        st.subheader("📋 Liste des points de livraison")
        
        df = pd.DataFrame(st.session_state.livraisons)
        
        # Affichage avec options de modification
        for idx, livraison in enumerate(st.session_state.livraisons):
            with st.expander(f"**{livraison['client']}** - {livraison['adresse']}", expanded=False):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    st.write(f"🕐 Fenêtre : **{livraison['heure_debut']} - {livraison['heure_fin']}**")
                    st.write(f"⏱️ Durée : **{livraison['duree']} min**")
                
                with col2:
                    st.write(f"📍 Coordonnées : {livraison['lat']:.4f}, {livraison['lng']:.4f}")
                    st.write(f"📊 Statut : {livraison['statut']}")
                
                with col3:
                    if st.button("🗑️ Supprimer", key=f"del_{idx}"):
                        st.session_state.livraisons.pop(idx)
                        st.rerun()
    
    # ============================================================
    # TAB 2 : CARTE INTERACTIVE
    # ============================================================
    with tab2:
        st.subheader("🗺️ Carte des livraisons")
        
        # Créer la carte centrée sur la Suisse
        centre_lat = sum(l['lat'] for l in st.session_state.livraisons) / len(st.session_state.livraisons)
        centre_lng = sum(l['lng'] for l in st.session_state.livraisons) / len(st.session_state.livraisons)
        
        m = folium.Map(location=[centre_lat, centre_lng], zoom_start=10)
        
        # Ajouter les marqueurs
        for idx, livraison in enumerate(st.session_state.livraisons, 1):
            folium.Marker(
                location=[livraison['lat'], livraison['lng']],
                popup=f"<b>{livraison['client']}</b><br>{livraison['adresse']}<br>🕐 {livraison['heure_debut']}-{livraison['heure_fin']}",
                tooltip=f"{idx}. {livraison['client']}",
                icon=folium.Icon(color='red', icon='info-sign', prefix='glyphicon')
            ).add_to(m)
        
        # Afficher la carte
        st_folium(m, width=700, height=500)
        
        # Calculer les distances entre points
        if len(st.session_state.livraisons) >= 2:
            st.markdown("---")
            st.subheader("📏 Matrice des distances")
            
            with st.spinner("Calcul des distances en cours..."):
                # Créer la matrice des distances
                origins = [(l['lat'], l['lng']) for l in st.session_state.livraisons]
                
                try:
                    distance_matrix = gmaps.distance_matrix(origins, origins, mode="driving")
                    
                    # Créer un DataFrame pour afficher
                    noms = [l['client'] for l in st.session_state.livraisons]
                    distances_km = []
                    
                    for i, row in enumerate(distance_matrix['rows']):
                        distances_ligne = []
                        for j, element in enumerate(row['elements']):
                            if element['status'] == 'OK':
                                dist_km = element['distance']['value'] / 1000
                                distances_ligne.append(f"{dist_km:.1f} km")
                            else:
                                distances_ligne.append("-")
                        distances_km.append(distances_ligne)
                    
                    df_distances = pd.DataFrame(distances_km, index=noms, columns=noms)
                    st.dataframe(df_distances, use_container_width=True)
                    
                except Exception as e:
                    st.error(f"❌ Erreur calcul distances : {str(e)}")
    
    # ============================================================
    # TAB 3 : ANALYSE
    # ============================================================
    with tab3:
        st.subheader("📊 Analyse de la tournée")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Graphique des horaires
            st.markdown("#### ⏰ Répartition des fenêtres horaires")
            
            df_horaires = pd.DataFrame(st.session_state.livraisons)
            df_horaires['heure_debut_num'] = df_horaires['heure_debut'].apply(
                lambda x: int(x.split(':')[0]) + int(x.split(':')[1])/60
            )
            
            fig = px.bar(df_horaires, x='client', y='duree', 
                        title="Durée par livraison",
                        labels={'duree': 'Durée (min)', 'client': 'Client'})
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Timeline des livraisons
            st.markdown("#### 📅 Timeline des créneaux")
            
            fig = go.Figure()
            
            for livraison in st.session_state.livraisons:
                heure_debut = datetime.strptime(livraison['heure_debut'], "%H:%M")
                heure_fin = datetime.strptime(livraison['heure_fin'], "%H:%M")
                
                fig.add_trace(go.Scatter(
                    x=[heure_debut, heure_fin],
                    y=[livraison['client'], livraison['client']],
                    mode='lines+markers',
                    name=livraison['client'],
                    line=dict(width=10)
                ))
            
            fig.update_layout(
                title="Fenêtres horaires disponibles",
                xaxis_title="Heure",
                yaxis_title="Client",
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    # ============================================================
    # TAB 4 : EXPORT
    # ============================================================
    with tab4:
        st.subheader("📥 Exporter les données")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📄 Format CSV")
            df_export = pd.DataFrame(st.session_state.livraisons)
            csv = df_export.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv,
                file_name=f"tournee_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            st.markdown("#### 🗺️ Lien Google Maps")
            
            # Créer l'URL Google Maps avec tous les points
            waypoints = []
            for livraison in st.session_state.livraisons:
                waypoints.append(f"{livraison['lat']},{livraison['lng']}")
            
            if waypoints:
                gmaps_url = f"https://www.google.com/maps/dir/{'/'.join(waypoints)}"
                st.markdown(f"[🔗 Ouvrir dans Google Maps]({gmaps_url})")
                
                if st.button("📋 Copier le lien", use_container_width=True):
                    st.code(gmaps_url)

st.markdown("---")
st.caption("💡 Application développée pour l'optimisation de tournées en Suisse")
