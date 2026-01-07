import streamlit as st
import googlemaps
import folium
# La correction principale est ici : importer PolyLine directement depuis folium
from folium import PolyLine
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import polyline as polyline_lib # Renommé pour éviter conflit si 'polyline' est utilisé ailleurs
import os

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Planificateur de Tournée Professionnelle",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TITRE DE L'APPLICATION ---
st.title("🚗 Planificateur de Tournée Professionnelle")

# --- INITIALISATION DE LA SESSION STATE ---
if 'stops' not in st.session_state:
    st.session_state.stops = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'mode_optimisation' not in st.session_state:
    st.session_state.mode_optimisation = "Livraisons avant Ramasses" # Valeur par défaut

# --- CONNEXION À L'API GOOGLE MAPS ---
try:
    api_key = st.secrets["google"]["api_key"]
    gmaps = googlemaps.Client(key=api_key)
except KeyError:
    st.error("Erreur : La clé API Google Maps n'est pas configurée. Veuillez la définir dans vos secrets Streamlit.")
    st.stop() # Arrête l'exécution si la clé n'est pas trouvée

# --- FONCTIONS UTILITAIRES ---

def get_coordinates(address):
    """Obtient les coordonnées (latitude, longitude) d'une adresse en utilisant Google Maps API."""
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            return geocode_result[0]['geometry']['location']['lat'], geocode_result[0]['geometry']['location']['lng']
        else:
            st.warning(f"Impossible de géocoder l'adresse : {address}")
            return None, None
    except Exception as e:
        st.error(f"Erreur lors du géocodage de {address}: {e}")
        return None, None

def format_duration(seconds):
    """Formate la durée en secondes en un string lisible (ex: 1h 30m)."""
    if seconds is None:
        return "N/A"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return f"{seconds}s"

def format_distance(meters):
    """Formate la distance en mètres en un string lisible (ex: 10.5 km)."""
    if meters is None:
        return "N/A"
    km = meters / 1000.0
    return f"{km:.1f} km"

def add_markers_to_map(m, stops, depot_coords):
    """Ajoute les marqueurs pour le dépôt et les arrêts sur la carte."""
    # Marqueur pour le dépôt
    if depot_coords:
        folium.Marker(
            location=depot_coords,
            popup="<b>Dépôt</b>",
            icon=folium.Icon(color='darkred', icon='home', prefix='fa')
        ).add_to(m)

    # Marqueurs pour les arrêts
    for i, stop in enumerate(stops):
        coords = get_coordinates(stop['address'])
        if coords:
            popup_html = f"""
            <b>Arrêt {i+1}</b><br>
            Adresse: {stop['address']}<br>
            Type: {'Ramasse' if stop['type'] == 'pickup' else 'Livraison'}<br>
            Fenêtre horaire: {stop.get('time_window_start', 'N/A')} - {stop.get('time_window_end', 'N/A')}<br>
            Durée visite: {stop.get('visit_duration', 'N/A')} min<br>
            Client: {stop.get('client_name', 'N/A')}<br>
            Notes: {stop.get('notes', '')}
            """
            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(color='blue' if stop['type'] == 'pickup' else 'green', icon='info-sign', prefix='glyphicon')
            ).add_to(m)

def calculate_directions_and_draw_route(m, stops, depot_address):
    """Calcule les directions entre les arrêts et les dessine sur la carte."""
    if not depot_address or not stops:
        st.warning("Veuillez définir un dépôt et ajouter des arrêts.")
        return

    depot_coords = get_coordinates(depot_address)
    if not depot_coords:
        st.error("Impossible de trouver les coordonnées du dépôt.")
        return

    # Préparer la liste des arrêts pour l'API Google Maps
    # Inclure le dépôt au début et à la fin pour le trajet complet
    waypoints = []
    for i, stop in enumerate(stops):
        coords = get_coordinates(stop['address'])
        if coords:
            waypoints.append({'location': coords, 'stopover': True, 'name': f"Arrêt {i+1} ({stop['type']})"})
        else:
            st.warning(f"Ignoré l'arrêt {stop['address']} car les coordonnées n'ont pas pu être obtenues.")

    if not waypoints:
        st.error("Aucun arrêt valide trouvé pour le calcul d'itinéraire.")
        return

    # --- Calcul des Directions avec Google Maps ---
    # L'ordre des waypoints dépendra du mode d'optimisation choisi par l'utilisateur.
    # Pour l'instant, on utilise l'ordre tel qu'il est entré, mais on pourrait le réordonner ici.

    # Tentative de récupérer l'heure actuelle pour departure_time
    now = datetime.now()
    
    st.write(f"Debug - Dépôt: {depot_address}, Coords: {depot_coords}")
    st.write(f"Debug - Arrêts à calculer: {len(waypoints)}")
    st.write(f"Debug - Mode optimisation: {st.session_state.mode_optimisation}")
    st.write(f"Debug - Départ prévu (datetime): {now}")


    try:
        # Appel à l'API Directions
        # Le paramètre 'waypoints' est une liste de dictionnaires.
        # L'ordre de 'waypoints' est crucial. Si on utilise optimize_waypoints=True, Google le fait.
        # Sinon, il faut que le tableau soit déjà trié.
        
        # On va gérer l'optimisation du tri ici en fonction du choix de l'utilisateur.
        # Pour l'instant, on suppose que les waypoints sont dans l'ordre désiré ou que optimize_waypoints=True est utilisé.
        
        # IMPORTANT : Le paramètre `departure_time` doit être un objet `datetime` ou un timestamp Unix.
        # Si `now` est déjà un objet `datetime`, c'est bon.
        
        directions_result = gmaps.directions(
            depot_coords,
            depot_coords, # Itinéraire du dépôt au dépôt, en passant par les waypoints
            mode="driving",
            waypoints=waypoints,
            departure_time=now, # Utilisation de l'objet datetime
            optimize_waypoints= st.session_state.mode_optimisation == "Optimisation par Google Maps" # Active si ce mode est choisi
        )

        if not directions_result:
            st.error("L'API Google Maps n'a retourné aucun résultat pour cet itinéraire.")
            return

        # --- Traitement des résultats ---
        route = directions_result[0] # Prend le premier itinéraire proposé

        # Extraction des données de l'itinéraire
        total_duration_seconds = route['legs'][0]['duration']['value']
        total_distance_meters = route['legs'][0]['distance']['value']
        
        # Afficher les informations de résumé de la tournée
        st.subheader("Résumé de la Tournée")
        col1, col2, col3 = st.columns(3)
        col1.metric("Durée Totale", format_duration(total_duration_seconds))
        col2.metric("Distance Totale", format_distance(total_distance_meters))
        # On pourrait calculer la durée sans les visites ici si nécessaire

        # Dessiner la route sur la carte
        if 'legs' in route:
            route_coords = []
            # Le premier 'leg' correspond au trajet Dépôt -> 1er Waypoint
            # Les 'legs' intermédiaires correspondent aux trajets entre waypoints
            # Le dernier 'leg' correspond au trajet dernier Waypoint -> Dépôt
            
            # On ajoute les coordonnées du dépôt de départ
            start_location = route['legs'][0]['start_location']
            route_coords.append((start_location['lat'], start_location['lng']))

            for leg in route['legs']:
                # Ajouter les points de la polyline du leg actuel
                decoded_polyline = polyline_lib.decode(leg['polyline']['points'])
                route_coords.extend(decoded_polyline)
                
                # Ajouter les coordonnées du point de fin du leg actuel (qui est le point de départ du leg suivant)
                # end_location = leg['end_location']
                # route_coords.append((end_location['lat'], end_location['lng']))

            # Créer une instance de PolyLine
            PolyLine(
                locations=route_coords,
                color='blue',
                weight=5,
                opacity=0.7
            ).add_to(m)
            
            # Ajouter un marqueur pour la fin du trajet (qui est le dépôt)
            end_location_final = route['legs'][-1]['end_location']
            folium.Marker(
                location=(end_location_final['lat'], end_location_final['lng']),
                popup="<b>Retour Dépôt</b>",
                icon=folium.Icon(color='darkred', icon='home', prefix='fa')
            ).add_to(m)

        else:
            st.warning("Les détails des 'legs' de l'itinéraire n'ont pas pu être récupérés.")

    except googlemaps.exceptions.ApiError as e:
        st.error(f"Erreur de l'API Google Maps : {e}")
        # Afficher des informations de débogage supplémentaires si possible
        st.error(f"Détails du problème : L'API Google Maps a retourné une erreur. Vérifiez que votre clé API est valide et que les paramètres envoyés sont corrects.")
        st.error(f"Paramètres envoyés au moment de l'erreur :")
        st.error(f"  - Départ: {depot_coords}")
        st.error(f"  - Waypoints: {waypoints}")
        st.error(f"  - Departure Time: {now} (Type: {type(now)})")
        st.error(f"  - Optimize Waypoints: {st.session_state.mode_optimisation == 'Optimisation par Google Maps'}")

    except TypeError as e:
        st.error(f"Erreur de Type : {e}")
        st.error("Cela indique souvent un problème avec le format des données passées à l'API, notamment pour 'departure_time'.")
        st.error(f"Vérifiez que 'now' est bien un objet datetime. Actuellement, 'now' est de type: {type(now)}")
        # Vous pouvez ajouter ici st.write(now) pour voir sa valeur exacte

    except Exception as e:
        st.error(f"Une erreur inattendue est survenue lors du calcul des directions : {e}")


# --- INTERFACE UTILISATEUR ---

# --- Section Dépôt ---
st.header("Étape 1 : Définir le Dépôt et les Arrêts")
st.subheader("Dépôt de départ")

depot_address = st.text_input("Adresse du dépôt :", key="depot_address", placeholder="Ex: 1 Rue de la République, Paris")

if depot_address:
    st.session_state.depot = depot_address
    depot_coords = get_coordinates(st.session_state.depot)
    if depot_coords:
        st.success(f"Dépôt localisé : {st.session_state.depot}")
else:
    st.session_state.depot = None
    depot_coords = None

st.markdown("---")

# --- Section Arrêts ---
st.subheader("Ajouter des arrêts")

# Colonnes pour une meilleure disposition des champs
col1_stop, col2_stop, col3_stop, col4_stop, col5_stop, col6_stop = st.columns(6)

with col1_stop:
    address = st.text_input("Adresse", key="stop_address", placeholder="Adresse de l'arrêt")
with col2_stop:
    stop_type = st.selectbox("Type", ["Livraison", "Ramasse"], key="stop_type")
with col3_stop:
    client_name = st.text_input("Client", key="client_name", placeholder="Nom du client")
with col4_stop:
    time_window_start = st.time_input("Début fenêtre", key="time_window_start", value=None, step=timedelta(minutes=15))
with col5_stop:
    time_window_end = st.time_input("Fin fenêtre", key="time_window_end", value=None, step=timedelta(minutes=15))
with col6_stop:
    visit_duration = st.number_input("Durée visite (min)", min_value=0, key="visit_duration", value=5)


notes = st.text_area("Notes / Instructions spéciales", key="stop_notes")

if st.button("Ajouter l'arrêt", key="add_stop_button"):
    if address and st.session_state.depot: # Vérifier si l'adresse et le dépôt sont renseignés
        # Convertir les valeurs de temps en format string si elles existent
        start_str = time_window_start.strftime("%H:%M") if time_window_start else None
        end_str = time_window_end.strftime("%H:%M") if time_window_end else None

        st.session_state.stops.append({
            'address': address,
            'type': 'delivery' if stop_type == "Livraison" else 'pickup',
            'client_name': client_name,
            'time_window_start': start_str,
            'time_window_end': end_str,
            'visit_duration': visit_duration,
            'notes': notes
        })
        st.success(f"Arrêt '{address}' ajouté.")
        # Réinitialiser les champs pour le prochain arrêt
        st.session_state.stop_address = ""
        st.session_state.stop_type = "Livraison"
        st.session_state.client_name = ""
        st.session_state.time_window_start = None
        st.session_state.time_window_end = None
        st.session_state.stop_notes = ""
        st.session_state.visit_duration = 5 # Réinitialiser à la valeur par défaut
    elif not address:
        st.warning("Veuillez entrer une adresse pour l'arrêt.")
    elif not st.session_state.depot:
        st.warning("Veuillez d'abord définir l'adresse du dépôt.")

# Affichage des arrêts ajoutés
if st.session_state.stops:
    st.subheader("Liste des arrêts prévus :")
    for i, stop in enumerate(st.session_state.stops):
        col_display_addr, col_display_type, col_display_client, col_display_time, col_display_duration, col_display_notes, col_delete = st.columns([3, 1, 1, 1, 1, 2, 0.5])
        
        with col_display_addr:
            st.write(f"{i+1}. {stop['address']}")
        with col_display_type:
            st.write(f"({stop['type']})")
        with col_display_client:
            st.write(f"{stop.get('client_name', '-')}")
        with col_display_time:
             st.write(f"{stop.get('time_window_start', '-')} - {stop.get('time_window_end', '-')}")
        with col_display_duration:
             st.write(f"{stop.get('visit_duration', '-')} min")
        with col_display_notes:
             st.write(f"{stop.get('notes', '-')}")
        with col_delete:
            if st.button("Suppr.", key=f"delete_stop_{i}"):
                st.session_state.stops.pop(i)
                st.rerun() # Rafraîchir pour mettre à jour la liste

st.markdown("---")

# --- Choix du mode d'optimisation et calcul ---
st.sidebar.header("Options d'Optimisation")
mode_optimisation = st.sidebar.radio(
    "Choisir le mode d'optimisation de la tournée :",
    ["Livraisons avant Ramasses", "Priorité Horaire", "Optimisation par Google Maps"],
    key="mode_optimisation"
)

# Option pour ramasses forcées à l'aller
if mode_optimisation == "Livraisons avant Ramasses":
    # Afficher l'option pour les ramasses forcées si ce mode est sélectionné
    # Cette logique doit être gérée dans la fonction qui calcule les directions
    # Pour l'instant, on la laisse comme une option générale qui affectera le traitement des waypoints.
    pass # On ne peut pas ajouter de checkbox ici car elle n'est pas liée à une variable de session directement
        # Il faudrait une variable de session dédiée, par exemple `force_pickup_on_outbound`

# Bouton pour calculer et afficher la tournée
if st.button("Calculer et Afficher la Tournée", key="calculate_route_button"):
    if st.session_state.depot and st.session_state.stops:
        # Créer une carte centrée sur le dépôt
        m = folium.Map(location=depot_coords, zoom_start=12)

        # Ajouter les marqueurs pour le dépôt et les arrêts
        add_markers_to_map(m, st.session_state.stops, depot_coords)

        # Calculer les directions et dessiner la route
        calculate_directions_and_draw_route(m, st.session_state.stops, st.session_state.depot)

        # Afficher la carte dans Streamlit
        st.subheader("Carte de la Tournée")
        folium_static(m, width=1000, height=500)

    elif not st.session_state.depot:
        st.warning("Veuillez d'abord définir l'adresse du dépôt.")
    else: # Pas de stops
        st.warning("Veuillez ajouter au moins un arrêt pour calculer la tournée.")

# --- Affichage de la carte initiale (optionnel) ---
# Pour afficher une carte vide au début si on le souhaite
# initial_map_center = [48.8566, 2.3522] # Coordonnées de Paris par défaut
# if st.session_state.depot:
#     initial_map_center = depot_coords
# elif st.session_state.stops:
#     first_stop_coords = get_coordinates(st.session_state.stops[0]['address'])
#     if first_stop_coords:
#         initial_map_center = first_stop_coords

# initial_map = folium.Map(location=initial_map_center, zoom_start=12)
# folium_static(initial_map, width=1000, height=500)


# --- EXPLICATION DES MODES D'OPTIMISATION (optionnel) ---
st.sidebar.subheader("Aide sur les Modes d'Optimisation")
st.sidebar.markdown("""
- **Livraisons avant Ramasses :** Optimise d'abord le trajet des livraisons, puis celui des ramasses. Utile si vous devez vider le camion avant de collecter.
- **Priorité Horaire :** Tente de minimiser les temps d'attente aux fenêtres horaires spécifiées. Plus complexe, nécessite des fenêtres horaires précises.
- **Optimisation par Google Maps :** Laisse Google Maps décider du meilleur ordre des arrêts pour minimiser le temps total du trajet Dépôt -> Tous les Points -> Dépôt.
""")

# --- EXPLICATION SUR LES RAMASSES FORCÉES ---
# Cette partie est une explication, la fonctionnalité réelle devrait être gérée dans le calcul
st.sidebar.subheader("Ramasses Forcées à l'Aller")
st.sidebar.markdown("""
Cocher cette case (lors de l'ajout d'une ramasse) indique à l'algorithme de la traiter comme une livraison dans le trajet aller.
Elle sera toujours affichée comme une ramasse, mais sa position dans le calcul sera plus proche du début de la tournée.
Utile si le client a spécifiquement besoin que vous passiez tôt pour récupérer un objet.
*(La fonctionnalité exacte dépend de l'implémentation du mode 'Livraisons avant Ramasses' ou d'une option dédiée)*
""")


# --- SECTION FOOTER ---
st.markdown("---")
st.markdown("Développé avec ❤️ par [Votre Nom/Équipe]")
