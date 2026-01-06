import streamlit as st
import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import folium
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta
import requests

# Configuration de la page
st.set_page_config(page_title="Optimisation Tournées", page_icon="🚚", layout="wide")

# Initialisation du géocodeur
geolocator = Nominatim(user_agent="tournee_livraison_app")

# Titre
st.title("🚚 Optimiseur de Tournées de Livraison")
st.markdown("*Application mobile-friendly pour chauffeurs poids-lourds*")

# ========== FONCTIONS UTILITAIRES ==========

def geocode_address(address):
    """Convertir une adresse en coordonnées GPS"""
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
        else:
            st.error(f"❌ Adresse introuvable : {address}")
            return None
    except Exception as e:
        st.error(f"Erreur géocodage : {e}")
        return None

def get_distance_matrix(coords):
    """Calculer les distances entre tous les points (via OpenRouteService)"""
    # Pour simplicité, on utilise la distance euclidienne * 1.3 (approximation route)
    n = len(coords)
    distances = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(0)
            else:
                # Distance euclidienne en km * 1000 (mètres) * 1.3 (coefficient route)
                lat1, lon1 = coords[i]
                lat2, lon2 = coords[j]
                dist = ((lat2 - lat1)**2 + (lon2 - lon1)**2)**0.5 * 111 * 1000 * 1.3
                row.append(int(dist))
        distances.append(row)
    return distances

def create_data_model(coords, time_windows, depot_idx=0):
    """Structure de données pour OR-Tools"""
    data = {}
    data['distance_matrix'] = get_distance_matrix(coords)
    data['time_windows'] = time_windows  # Format: [(debut_minutes, fin_minutes), ...]
    data['num_vehicles'] = 1
    data['depot'] = depot_idx
    data['vehicle_capacity'] = 25000  # Poids max en kg
    data['demands'] = [0] + [100] * (len(coords) - 1)  # 0 pour dépôt, 100kg par client
    return data

def solve_vrp(data):
    """Résoudre le problème d'optimisation avec OR-Tools"""
    manager = pywrapcp.RoutingIndexManager(
        len(data['distance_matrix']),
        data['num_vehicles'],
        data['depot']
    )
    routing = pywrapcp.RoutingModel(manager)

    # Fonction de coût (distance)
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Contrainte de capacité
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [data['vehicle_capacity']],  # vehicle maximum capacities
        True,  # start cumul to zero
        'Capacity'
    )

    # Contrainte de temps (fenêtres horaires)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        travel_time = data['distance_matrix'][from_node][to_node] // 500  # Vitesse ~30km/h
        service_time = 15  # 15 min par livraison
        return travel_time + service_time

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_callback_index,
        60,  # Marge de 60 minutes
        1440,  # Journée de 24h (en minutes)
        False,
        'Time'
    )

    time_dimension = routing.GetDimensionOrDie('Time')
    for location_idx, time_window in enumerate(data['time_windows']):
        if location_idx == data['depot']:
            continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])

    # Paramètres de recherche
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.time_limit.seconds = 10

    # Résolution
    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        return extract_solution(manager, routing, solution, data)
    else:
        return None

def extract_solution(manager, routing, solution, data):
    """Extraire l'itinéraire optimisé"""
    time_dimension = routing.GetDimensionOrDie('Time')
    index = routing.Start(0)
    route = []
    
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        time_var = time_dimension.CumulVar(index)
        arrival_time = solution.Min(time_var)
        route.append((node_index, arrival_time))
        index = solution.Value(routing.NextVar(index))
    
    # Ajouter le retour au dépôt
    node_index = manager.IndexToNode(index)
    time_var = time_dimension.CumulVar(index)
    route.append((node_index, solution.Min(time_var)))
    
    return route

def create_map(coords, route, addresses):
    """Créer une carte Folium avec l'itinéraire"""
    # Centre de la carte
    center = [sum([c[0] for c in coords])/len(coords), 
              sum([c[1] for c in coords])/len(coords)]
    
    m = folium.Map(location=center, zoom_start=12)
    
    # Marqueurs
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
              'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'pink']
    
    for idx, (stop, _) in enumerate(route):
        coord = coords[stop]
        color = 'red' if stop == 0 else colors[idx % len(colors)]
        icon = 'home' if stop == 0 else 'shopping-cart'
        
        folium.Marker(
            coord,
            popup=f"<b>{'DÉPÔT' if stop == 0 else addresses[stop]}</b><br>Arrêt n°{idx+1}",
            icon=folium.Icon(color=color, icon=icon),
            tooltip=f"Arrêt {idx+1}"
        ).add_to(m)
    
    # Ligne de route
    route_coords = [coords[stop] for stop, _ in route]
    folium.PolyLine(route_coords, color='blue', weight=3, opacity=0.7).add_to(m)
    
    return m

def minutes_to_time(minutes, start_time):
    """Convertir minutes en heure lisible"""
    time = start_time + timedelta(minutes=minutes)
    return time.strftime("%H:%M")

def generate_google_maps_url(coords, route):
    """Générer URL Google Maps avec waypoints"""
    base_url = "https://www.google.com/maps/dir/?api=1"
    origin = f"{coords[route[0][0]][0]},{coords[route[0][0]][1]}"
    destination = f"{coords[route[-1][0]][0]},{coords[route[-1][0]][1]}"
    
    waypoints = "|".join([f"{coords[stop][0]},{coords[stop][1]}" 
                          for stop, _ in route[1:-1]])
    
    url = f"{base_url}&origin={origin}&destination={destination}&waypoints={waypoints}&travelmode=driving"
    return url

# ========== INTERFACE STREAMLIT ==========

# Sidebar pour les paramètres
with st.sidebar:
    st.header("⚙️ Paramètres")
    heure_debut = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
    vitesse_moy = st.slider("Vitesse moyenne (km/h)", 20, 60, 30)
    temps_service = st.number_input("Temps par livraison (min)", 5, 60, 15)
    
    st.markdown("---")
    st.markdown("**📍 Mode saisie**")
    mode_saisie = st.radio("", ["Adresses", "GPS (Lat/Long)"])

# Zone de saisie principale
st.subheader("📝 Entrer les livraisons")

# Exemple de données
with st.expander("📋 Voir un exemple"):
    st.code("""
DÉPÔT, 48.8566, 2.3522, 08:00, 08:00
Client A, 48.8606, 2.3376, 09:00, 11:00
Client B, 48.8529, 2.3499, 10:00, 12:00
Client C, 48.8584, 2.2945, 08:30, 09:30
Client D, 48.8738, 2.2950, 14:00, 16:00
    """)
    st.caption("Format : Nom, Latitude, Longitude, Heure début, Heure fin")

if mode_saisie == "Adresses":
    data_input = st.text_area(
        "Format : `Nom | Adresse | Heure début | Heure fin` (une ligne par client)",
        height=200,
        placeholder="DÉPÔT | 5 Rue de Paris 75001 | 08:00 | 08:00\nClient A | 10 Avenue des Champs 75008 | 09:00 | 11:00"
    )
else:
    data_input = st.text_area(
        "Format : `Nom | Latitude | Longitude | Heure début | Heure fin`",
        height=200,
        placeholder="DÉPÔT | 48.8566 | 2.3522 | 08:00 | 08:00\nClient A | 48.8606 | 2.3376 | 09:00 | 11:00"
    )

# Bouton d'optimisation
if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary", use_container_width=True):
    if not data_input.strip():
        st.error("❌ Veuillez entrer au moins 2 points (dépôt + 1 client)")
    else:
        with st.spinner("⏳ Calcul en cours..."):
            try:
                # Parser les données
                lines = [l.strip() for l in data_input.split('\n') if l.strip()]
                addresses = []
                coords = []
                time_windows = []
                
                start_datetime = datetime.combine(datetime.today(), heure_debut)
                
                for line in lines:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) != 5:
                        st.error(f"❌ Format incorrect : {line}")
                        st.stop()
                    
                    nom = parts[0]
                    addresses.append(nom)
                    
                    if mode_saisie == "Adresses":
                        coord = geocode_address(parts[1])
                        if not coord:
                            st.stop()
                        coords.append(coord)
                    else:
                        coords.append((float(parts[1]), float(parts[2])))
                    
                    # Convertir heures en minutes depuis le début
                    h_debut = datetime.strptime(parts[3], "%H:%M")
                    h_fin = datetime.strptime(parts[4], "%H:%M")
                    
                    min_debut = (h_debut.hour - heure_debut.hour) * 60 + h_debut.minute
                    min_fin = (h_fin.hour - heure_debut.hour) * 60 + h_fin.minute
                    
                    time_windows.append((max(0, min_debut), min_fin))
                
                # Créer le modèle et résoudre
                data = create_data_model(coords, time_windows)
                solution = solve_vrp(data)
                
                if solution:
                    st.success("✅ Tournée optimisée avec succès !")
                    
                    # Afficher le résultat
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        st.subheader("📋 Ordre de livraison")
                        df_results = []
                        for idx, (stop, arrival_min) in enumerate(solution):
                            df_results.append({
                                "N°": idx + 1,
                                "Client": addresses[stop],
                                "Heure": minutes_to_time(arrival_min, start_datetime)
                            })
                        
                        st.dataframe(
                            pd.DataFrame(df_results),
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        # Statistiques
                        total_dist = sum([
                            data['distance_matrix'][solution[i][0]][solution[i+1][0]]
                            for i in range(len(solution)-1)
                        ]) / 1000
                        
                        st.metric("Distance totale", f"{total_dist:.1f} km")
                        st.metric("Temps total", f"{(solution[-1][1] - solution[0][1])} min")
                        
                        # Bouton Google Maps
                        maps_url = generate_google_maps_url(coords, solution)
                        st.link_button(
                            "🗺️ OUVRIR DANS GOOGLE MAPS",
                            maps_url,
                            use_container_width=True
                        )
                    
                    with col2:
                        st.subheader("🗺️ Carte interactive")
                        m = create_map(coords, solution, addresses)
                        folium_static(m, width=400, height=500)
                    
                else:
                    st.error("❌ Impossible de trouver une solution. Vérifiez les fenêtres horaires.")
                    
            except Exception as e:
                st.error(f"❌ Erreur : {str(e)}")
                st.exception(e)

# Footer
st.markdown("---")
st.caption("🚚 Application créée avec Streamlit | Optimisation via OR-Tools")
