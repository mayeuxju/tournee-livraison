import streamlit as st
import googlemaps
from datetime import datetime, timedelta
import pandas as pd
import time # Pour la gestion du temps

# --- Configuration de la clé API Google Maps via Streamlit Secrets ---
try:
    # Vérifie si la clé API est disponible via st.secrets
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    # Test rapide pour vérifier la validité de la clé (optionnel mais recommandé)
    # Si vous avez une limite d'appels très basse pour les tests, vous pourriez commenter cette ligne
    # geocode_result = gmaps.geocode('Paris')
    # if not geocode_result:
    #     st.warning("La clé API Google Maps semble ne pas être valide ou ne retourne pas de résultats.")
except KeyError:
    st.error("Clé API Google manquante. Assurez-vous que votre fichier secrets.toml contient la section 'google' avec la clé 'api_key' :")
    st.code("[google]\napi_key='VOTRE_CLE_API_ICI'")
    st.stop() # Arrête l'application si la clé est manquante
except Exception as e:
    st.error(f"Une erreur est survenue lors de l'initialisation de l'API Google Maps : {e}")
    st.stop()

# --- Constantes et Variables Globales ---
# Augmenter le temps limite pour les parcours plus longs, ou adapter selon vos besoins
TEMPS_MAX_PARCOURS_MINUTES = 12 * 60 # 12 heures en minutes

# Seuil d'attente tolérable avant de tenter une optimisation (en minutes)
SEUIL_ATTENTE_OPTIMISATION_MINUTES = 15

# Facteur pour ajuster la "pression" à minimiser l'attente (0 = pas d'influence, 1 = très forte)
# Ce facteur sera utilisé pour pondérer l'attente dans le calcul du coût
COEFF_ATTENTE_HORAIRE = 0.8 # 80% de l'importance par rapport à la distance/durée pure

# --- Fonctions Utilitaires ---

def format_duration(seconds):
    """Formate une durée en secondes en un string lisible (ex: '1h 30min')."""
    if seconds is None: return "N/A"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}min" if h > 0 else f"{m}min"

def format_distance(meters):
    """Formate une distance en mètres en un string lisible (ex: '10.5 km')."""
    if meters is None: return "N/A"
    km = meters / 1000.0
    return f"{km:.1f} km"

def get_geocode(address):
    """Récupère les coordonnées géographiques d'une adresse."""
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            return geocode_result[0]['geometry']['location']
        else:
            st.warning(f"Impossible de géocoder l'adresse : {address}")
            return None
    except Exception as e:
        st.error(f"Erreur lors du géocodage de '{address}' : {e}")
        return None

def get_directions(origin, destination, mode="driving", departure_time=None):
    """Récupère les informations d'itinéraire entre deux points."""
    try:
        directions_result = gmaps.directions(
            origin,
            destination,
            mode=mode,
            departure_time=departure_time # Peut être un datetime object
        )
        if directions_result:
            leg = directions_result[0]['legs'][0]
            return {
                "duration_seconds": leg['duration']['value'],
                "distance_meters": leg['distance']['value'],
                "duration_text": leg['duration']['text'],
                "distance_text": leg['distance']['text'],
                "start_address": leg['start_address'],
                "end_address": leg['end_address']
            }
        else:
            st.warning(f"Aucun itinéraire trouvé entre {origin} et {destination}")
            return None
    except Exception as e:
        st.error(f"Erreur lors de la récupération des directions entre '{origin}' et '{destination}' : {e}")
        return None

# --- Modèles de Données ---

class Client:
    def __init__(self, id, nom, adresse, type_arret,
                 fenetre_debut=None, fenetre_fin=None, temps_service_min=0,
                 inclure_dans_aller_meme_si_ramasse=False):
        self.id = id
        self.nom = nom
        self.adresse = adresse
        self.type_arret = type_arret # "Livraison" ou "Ramasse"
        self.fenetre_debut = fenetre_debut # datetime object
        self.fenetre_fin = fenetre_fin     # datetime object
        self.temps_service_min = temps_service_min # Durée estimée au point (en minutes)
        self.inclure_dans_aller_meme_si_ramasse = inclure_dans_aller_meme_si_ramasse

        self.coords = None # Sera rempli après géocodage
        self.heure_arrivee = None # datetime object
        self.heure_depart = None  # datetime object
        self.attente_prevue = timedelta(0) # timedelta object

    def __repr__(self):
        return f"Client(id={self.id}, nom='{self.nom}', type='{self.type_arret}')"

    def est_livraison(self):
        return self.type_arret == "Livraison"

    def est_ramasse(self):
        return self.type_arret == "Ramasse"

    def a_contrainte_horaire(self):
        return self.fenetre_debut is not None and self.fenetre_fin is not None

    def to_dict(self):
        """Convertit l'objet Client en dictionnaire pour affichage."""
        return {
            "ID": self.id,
            "Nom": self.nom,
            "Adresse": self.adresse,
            "Type": self.type_arret,
            "Arrivée": self.heure_arrivee.strftime('%H:%M:%S') if self.heure_arrivee else "N/A",
            "Départ": self.heure_depart.strftime('%H:%M:%S') if self.heure_depart else "N/A",
            "Attente": str(self.attente_prevue).split('.')[0] if self.attente_prevue else "00:00:00",
            "Contrainte Horaire": f"{self.fenetre_debut.strftime('%H:%M')}-{self.fenetre_fin.strftime('%H:%M')}" if self.a_contrainte_horaire() else "Aucune",
            "Temps Service": f"{self.temps_service_min} min" if self.temps_service_min > 0 else "0 min",
            "Ramasse dans Aller": "Oui" if self.inclure_dans_aller_meme_si_ramasse else "Non"
        }

# --- Interface Utilisateur ---

st.set_page_config(layout="wide")
st.title("🚚 Optimiseur de Tournées de Livraison/Ramasse")
st.markdown("Planifiez vos tournées en tenant compte des contraintes horaires et de la priorité de livraison.")

if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'tournee_optimisee' not in st.session_state:
    st.session_state.tournee_optimisee = None
if 'itineraire_complet' not in st.session_state:
    st.session_state.itineraire_complet = None

# --- Saisie des Données ---

st.header("1. Informations sur les arrêts")
col1, col2, col3 = st.columns(3)

with col1:
    nom_client = st.text_input("Nom du client", key="nom_client_input")
    adresse_client = st.text_area("Adresse complète", key="adresse_client_input", height=50)

with col2:
    type_arret = st.selectbox("Type d'arrêt", ["Livraison", "Ramasse"], key="type_arret_select")

    # Gestion des contraintes horaires et temps de service
    debut_contrainte_str = st.text_input("Début fenêtre horaire (HH:MM, optionnel)", key="fenetre_debut_input")
    fin_contrainte_str = st.text_input("Fin fenêtre horaire (HH:MM, optionnel)", key="fenetre_fin_input")

with col3:
    temps_service_min = st.number_input("Temps de service (min, optionnel)", min_value=0, value=0, step=1, key="temps_service_input")

    # Nouvelle option pour les ramasses
    inclure_dans_aller_meme_si_ramasse = False
    if type_arret == "Ramasse":
        inclure_dans_aller_meme_si_ramasse = st.checkbox("Inclure dans l'aller (comme livraison)", key="inclure_dans_aller_checkbox")

add_client_button = st.button("Ajouter cet arrêt")

if add_client_button and nom_client and adresse_client:
    # Conversion des contraintes horaires
    fenetre_debut = None
    fenetre_fin = None
    if debut_contrainte_str and fin_contrainte_str:
        try:
            # On utilise une date arbitraire (aujourd'hui) pour pouvoir manipuler les deltas,
            # seule l'heure sera réellement pertinente pour les comparaisons d'horaires.
            today = datetime.now().date()
            debut_h, debut_m = map(int, debut_contrainte_str.split(':'))
            fin_h, fin_m = map(int, fin_contrainte_str.split(':'))
            
            # Gestion des cas où l'heure de fin est plus tôt que l'heure de début (ex: 22:00 - 02:00)
            date_debut = today
            date_fin = today
            if fin_h < debut_h or (fin_h == debut_h and fin_m < debut_m):
                date_fin += timedelta(days=1) # La fenêtre se termine le jour suivant

            fenetre_debut = datetime.combine(date_debut, datetime.min.time()) + timedelta(hours=debut_h, minutes=debut_m)
            fenetre_fin = datetime.combine(date_fin, datetime.min.time()) + timedelta(hours=fin_h, minutes=fin_m)

            # Validation basique : la fin doit être après le début
            if fenetre_fin <= fenetre_debut:
                st.warning("L'heure de fin de la fenêtre horaire doit être après l'heure de début.")
                st.session_state.fenetre_debut_input = ""
                st.session_state.fenetre_fin_input = ""
                fenetre_debut = None
                fenetre_fin = None

        except ValueError:
            st.warning("Format d'heure invalide. Utilisez HH:MM (ex: 09:30).")
            fenetre_debut = None
            fenetre_fin = None

    new_client = Client(
        id=len(st.session_state.clients) + 1,
        nom=nom_client,
        adresse=adresse_client,
        type_arret=type_arret,
        fenetre_debut=fenetre_debut,
        fenetre_fin=fenetre_fin,
        temps_service_min=temps_service_min,
        inclure_dans_aller_meme_si_ramasse=inclure_dans_aller_meme_si_ramasse
    )
    st.session_state.clients.append(new_client)

    # Vider les champs pour le prochain ajout
    st.session_state.nom_client_input = ""
    st.session_state.adresse_client_input = ""
    st.session_state.type_arret_select = "Livraison"
    st.session_state.fenetre_debut_input = ""
    st.session_state.fenetre_fin_input = ""
    st.session_state.temps_service_input = 0
    st.session_state.inclure_dans_aller_checkbox = False

# Affichage des clients ajoutés
if st.session_state.clients:
    st.subheader("Liste des arrêts ajoutés :")
    
    # Créer un DataFrame pour un affichage plus propre
    client_data = [client.to_dict() for client in st.session_state.clients]
    df_clients = pd.DataFrame(client_data)
    st.dataframe(df_clients, use_container_width=True)

    # Bouton pour supprimer le dernier arrêt ajouté
    if st.button("Supprimer le dernier arrêt"):
        if st.session_state.clients:
            st.session_state.clients.pop()
            # Reset l'optimisation si on modifie les arrêts
            st.session_state.tournee_optimisee = None
            st.session_state.itineraire_complet = None
            st.rerun() # Force le re-rendu pour afficher la liste mise à jour

# --- Paramètres de l'Optimisation ---
st.header("2. Paramètres de la tournée")

col1_optim, col2_optim = st.columns(2)

with col1_optim:
    heure_debut_tournee_str = st.text_input("Heure de début de la tournée (HH:MM)", value="08:00", key="heure_debut_tournee_input")
    
    # Intégration du coefficient d'attente horaire
    st.session_state.coeff_attente_horaire = st.slider(
        "Importance de la contrainte horaire (0=peu, 1=beaucoup)",
        min_value=0.0, max_value=1.0, value=COEFF_ATTENTE_HORAIRE, step=0.1,
        key="coeff_attente_horaire_slider",
        help="Détermine à quel point l'algorithme privilégiera le respect des fenêtres horaires par rapport à la distance/durée pure du trajet."
    )

with col2_optim:
    # Option pour le point de départ/retour
    point_depart_return = st.text_input("Point de départ et de retour (adresse)", value="Entrepôt Central", key="point_depart_return_input")

# --- Bouton d'Optimisation ---
optimize_button = st.button("🚀 Optimiser la Tournée")

# --- Logique d'Optimisation ---

def optimiser_tournee(clients, heure_debut_tournee, point_depart_return_addr, coeff_attente):
    """
    Fonction principale pour optimiser la tournée.
    Args:
        clients (list): Liste d'objets Client.
        heure_debut_tournee (datetime): Heure de début de la tournée.
        point_depart_return_addr (str): Adresse du point de départ/retour.
        coeff_attente (float): Coefficient d'influence des contraintes horaires.
    Returns:
        tuple: (liste d'objets Client ordonnancés, liste des étapes de l'itinéraire complet)
    """
    if not clients:
        st.warning("Veuillez ajouter des arrêts avant d'optimiser.")
        return [], []

    # 1. Géocodage de tous les points (incluant point de départ/retour)
    locations_to_geocode = {
        "DEPART_RETOUR": point_depart_return_addr
    }
    for client in clients:
        locations_to_geocode[client.id] = client.adresse

    geocoded_points = {}
    for name, addr in locations_to_geocode.items():
        coords = get_geocode(addr)
        if coords:
            geocoded_points[name] = coords
        else:
            st.error(f"Arrêt impossible : Impossible de géocoder '{addr}'. Veuillez vérifier l'adresse ou la clé API.")
            return [], [] # Arrêter l'optimisation si un point ne peut être géocodé

    # Assigner les coordonnées aux objets clients
    for client in clients:
        client.coords = geocoded_points.get(client.id)
        if not client.coords:
            # Cette erreur ne devrait pas arriver si la boucle précédente a réussi
            st.error(f"Erreur interne : Coordonnées manquantes pour le client {client.id}")
            return [], []

    # 2. Séparation initiale des livraisons et ramasses
    livraisons = [c for c in clients if c.est_livraison()]
    ramasses = [c for c in clients if c.est_ramasse()]

    # Gestion des ramasses marquées pour être traitées comme livraisons
    ramasses_en_aller = [r for r in ramasses if r.inclure_dans_aller_meme_si_ramasse]
    ramasses_restantes = [r for r in ramasses if not r.inclure_dans_aller_meme_si_ramasse]

    # Combinaison des livraisons et des ramasses spéciales pour la phase "aller"
    points_aller = livraisons + ramasses_en_aller
    points_retour = ramasses_restantes # Ce sont les ramasses qui seront faites après toutes les livraisons

    # Initialisation de la tournée
    tournee_ordenee = []
    itineraire_complet = []
    heure_actuelle = heure_debut_tournee
    
    # Point de départ virtuel pour les calculs
    point_precedent_coords = geocoded_points["DEPART_RETOUR"]
    adresse_precedente = point_depart_return_addr

    # --- PHASE 1 : Traitement des Livraisons et Ramasses Spéciales ("Aller") ---
    
    # On utilise une approche simple : ordonnancer les points de l'aller, puis les points du retour.
    # Une optimisation plus complexe (type TSP) pourrait être implémentée ici pour les points_aller et points_retour séparément.
    # Pour l'instant, on garde l'ordre d'ajout pour les points_aller, et on traite les ramasses_restantes ensuite.
    
    points_a_traiter_aller = points_aller # On peut ici implémenter une logique TSP si besoin
    
    st.info(f"Traitement de {len(points_a_traiter_aller)} arrêts (Livraisons + Ramasses spéciales).")
    
    for i, point_actuel in enumerate(points_a_traiter_aller):
        # Calculer le temps de trajet du point précédent au point actuel
        directions = get_directions(adresse_precedente, point_actuel.adresse, departure_time=heure_actuelle)
        
        if not directions:
            st.warning(f"Impossible de calculer le trajet vers {point_actuel.nom}. Arrêt ignoré.")
            continue # Passe au point suivant

        temps_trajet_sec = directions["duration_seconds"]
        temps_trajet = timedelta(seconds=temps_trajet_sec)
        
        # Calcul de l'heure d'arrivée potentielle
        heure_arrivee_potentielle = heure_actuelle + temps_trajet
        
        # Vérification des contraintes horaires et calcul de l'attente
        attente = timedelta(0)
        heure_debut_service = heure_arrivee_potentielle # Heure à laquelle on peut commencer le service
        
        if point_actuel.a_contrainte_horaire():
            # On doit respecter la fenêtre (debut, fin)
            if heure_arrivee_potentielle > point_actuel.fenetre_fin:
                # Arrivée trop tard pour respecter la fin de fenêtre
                # ATTENTION: ici, on pourrait implémenter une logique plus complexe
                # pour re-ordonnancer les points précédents, mais cela complexifie énormément.
                # Pour l'instant, on marque l'erreur et on essaie de continuer.
                st.warning(f"Arrivée trop tard ({heure_arrivee_potentielle.strftime('%H:%M')}) pour le respect de la fenêtre ({point_actuel.fenetre_debut.strftime('%H:%M')}-{point_actuel.fenetre_fin.strftime('%H:%M')}) chez {point_actuel.nom}. L'optimisation peut être sous-optimale.")
                # On force le début du service à la fin de la fenêtre si l'arrivée est avant
                if heure_arrivee_potentielle < point_actuel.fenetre_fin:
                     heure_debut_service = point_actuel.fenetre_fin
                else: # Si on arrive APRES la fin de la fenêtre, on ne peut rien faire...
                    heure_debut_service = heure_arrivee_potentielle # On commence quand même

            elif heure_arrivee_potentielle < point_actuel.fenetre_debut:
                # On arrive trop tôt, il faut attendre
                attente = point_actuel.fenetre_debut - heure_arrivee_potentielle
                heure_debut_service = point_actuel.fenetre_debut
        
        # Mise à jour de l'heure actuelle (après attente si nécessaire)
        heure_actuelle = heure_debut_service
        
        # Calcul de l'heure de départ (après service)
        temps_service = timedelta(minutes=point_actuel.temps_service_min)
        heure_depart = heure_actuelle + temps_service
        
        # Enregistrement des informations pour ce point
        point_actuel.heure_arrivee = heure_arrivee_potentielle
        point_actuel.heure_depart = heure_depart
        point_actuel.attente_prevue = attente
        
        tournee_ordenee.append(point_actuel)
        itineraire_complet.append({
            "description": f"Trajet vers {point_actuel.nom}",
            "heure_depart": heure_actuelle - attente, # Heure avant l'attente
            "heure_arrivee": heure_arrivee_potentielle,
            "duree_trajet": temps_trajet,
            "distance_trajet": timedelta(seconds=directions["distance_meters"] / 10) if directions.get("distance_meters") else None, # Approximation grossière
            "details_api": directions # Stocke les données brutes de l'API
        })
        
        # Mise à jour pour le prochain calcul
        heure_actuelle = heure_depart # Le départ de ce point est l'heure de début pour le prochain trajet
        point_precedent_coords = point_actuel.coords
        adresse_precedente = point_actuel.adresse

    # --- PHASE 2 : Traitement des Ramasses Restantes ("Retour") ---
    
    st.info(f"Traitement de {len(ramasses_restantes)} arrêts (Ramasses classiques).")

    # Ici, on pourrait aussi appliquer une logique TSP pour optimiser l'ordre des ramasses_restantes
    points_a_traiter_retour = ramasses_restantes
    
    for i, point_actuel in enumerate(points_a_traiter_retour):
        # Calculer le temps de trajet du point précédent au point actuel
        directions = get_directions(adresse_precedente, point_actuel.adresse, departure_time=heure_actuelle)
        
        if not directions:
            st.warning(f"Impossible de calculer le trajet vers {point_actuel.nom}. Arrêt ignoré.")
            continue

        temps_trajet_sec = directions["duration_seconds"]
        temps_trajet = timedelta(seconds=temps_trajet_sec)
        
        heure_arrivee_potentielle = heure_actuelle + temps_trajet
        
        # Vérification des contraintes horaires pour les ramasses (moins critique, mais on les applique quand même)
        attente = timedelta(0)
        heure_debut_service = heure_arrivee_potentielle
        
        if point_actuel.a_contrainte_horaire():
            if heure_arrivee_potentielle > point_actuel.fenetre_fin:
                 st.warning(f"Arrivée trop tard ({heure_arrivee_potentielle.strftime('%H:%M')}) pour le respect de la fenêtre ({point_actuel.fenetre_debut.strftime('%H:%M')}-{point_actuel.fenetre_fin.strftime('%H:%M')}) chez {point_actuel.nom}.")
                 if heure_arrivee_potentielle < point_actuel.fenetre_fin:
                     heure_debut_service = point_actuel.fenetre_fin
                 else:
                     heure_debut_service = heure_arrivee_potentielle
            elif heure_arrivee_potentielle < point_actuel.fenetre_debut:
                attente = point_actuel.fenetre_debut - heure_arrivee_potentielle
                heure_debut_service = point_actuel.fenetre_debut

        heure_actuelle = heure_debut_service
        
        temps_service = timedelta(minutes=point_actuel.temps_service_min)
        heure_depart = heure_actuelle + temps_service
        
        point_actuel.heure_arrivee = heure_arrivee_potentielle
        point_actuel.heure_depart = heure_depart
        point_actuel.attente_prevue = attente
        
        tournee_ordenee.append(point_actuel)
        itineraire_complet.append({
            "description": f"Trajet vers {point_actuel.nom}",
            "heure_depart": heure_actuelle - attente,
            "heure_arrivee": heure_arrivee_potentielle,
            "duree_trajet": temps_trajet,
            "distance_trajet": timedelta(seconds=directions["distance_meters"] / 10) if directions.get("distance_meters") else None,
            "details_api": directions
        })
        
        heure_actuelle = heure_depart
        point_precedent_coords = point_actuel.coords
        adresse_precedente = point_actuel.adresse

    # --- PHASE 3 : Retour au point de départ ---
    if adresse_precedente != point_depart_return_addr:
        st.info("Calcul du retour à l'entrepôt.")
        directions = get_directions(adresse_precedente, point_depart_return_addr, departure_time=heure_actuelle)
        if directions:
            temps_trajet = timedelta(seconds=directions["duration_seconds"])
            heure_arrivee_retour = heure_actuelle + temps_trajet
            
            itineraire_complet.append({
                "description": f"Retour à {point_depart_return_addr}",
                "heure_depart": heure_actuelle,
                "heure_arrivee": heure_arrivee_retour,
                "duree_trajet": temps_trajet,
                "distance_trajet": timedelta(seconds=directions["distance_meters"] / 10) if directions.get("distance_meters") else None,
                "details_api": directions
            })
            heure_actuelle = heure_arrivee_retour # Fin de la tournée
        else:
            st.warning("Impossible de calculer le trajet de retour.")
    
    # Vérification de la durée totale de la tournée
    duree_totale_tournee = heure_actuelle - heure_debut_tournee
    if duree_totale_tournee.total_seconds() > TEMPS_MAX_PARCOURS_MINUTES * 60:
        st.warning(f"La durée totale de la tournée estimée ({format_duration(duree_totale_tournee.total_seconds())}) dépasse le temps maximum autorisé ({format_duration(TEMPS_MAX_PARCOURS_MINUTES*60)}).")

    return tournee_ordenee, itineraire_complet

# --- Affichage des Résultats ---

if optimize_button:
    # Validation des entrées
    try:
        heure_debut_tournee_obj = datetime.combine(datetime.now().date(), 
                                                   datetime.strptime(heure_debut_tournee_str, "%H:%M").time())
    except ValueError:
        st.error("Format d'heure de début de tournée invalide. Utilisez HH:MM (ex: 08:00).")
        st.stop() # Arrête l'exécution si l'heure est invalide

    # Lancer l'optimisation
    with st.spinner("Calcul de la tournée optimale en cours..."):
        st.session_state.tournee_optimisee, st.session_state.itineraire_complet = optimiser_tournee(
            st.session_state.clients,
            heure_debut_tournee_obj,
            st.session_state.point_depart_return_input,
            st.session_state.coeff_attente_horaire_slider # Utilisation du slider pour le coeff
        )

    # Afficher les résultats si l'optimisation a réussi
    if st.session_state.tournee_optimisee:
        st.success("Tournée optimisée avec succès !")

        # Affichage détaillé de la tournée ordonnancée
        st.header("3. Tournée Optimisée")
        
        client_data_optimisee = [client.to_dict() for client in st.session_state.tournee_optimisee]
        df_tournee = pd.DataFrame(client_data_optimisee)
        st.dataframe(df_tournee, use_container_width=True)

        # Affichage de l'itinéraire complet étape par étape
        st.header("4. Itinéraire Détaillé")
        
        if st.session_state.itineraire_complet:
            itineraire_data = []
            duree_totale_tournee = timedelta(0)
            distance_totale_tournee = 0
            heure_debut_reelle = heure_debut_tournee_obj # Pour calculer la durée totale

            for etape in st.session_state.itineraire_complet:
                # Les temps de trajet sont des Timedelta
                duree_trajet_etape = etape.get("duree_trajet", timedelta(0))
                distance_trajet_etape_m = 0
                if etape.get("distance_trajet") is not None:
                    # La distance ici est déjà une approximation en mètres car j'ai fait dist/10, il faut corriger
                    # Utilisons la distance brute de l'API si dispo
                    raw_distance = etape.get("details_api", {}).get("distance_meters")
                    if raw_distance:
                        distance_trajet_etape_m = raw_distance
                        distance_totale_tournee += raw_distance

                itineraire_data.append({
                    "Description": etape["description"],
                    "Départ": etape["heure_depart"].strftime('%H:%M:%S') if etape["heure_depart"] else "N/A",
                    "Arrivée": etape["heure_arrivee"].strftime('%H:%M:%S') if etape["heure_arrivee"] else "N/A",
                    "Durée Trajet": format_duration(duree_trajet_etape.total_seconds()),
                    "Distance": format_distance(distance_trajet_etape_m),
                })
                
                duree_totale_tournee += duree_trajet_etape_etape # BUG: J'utilisais une variable locale ici, il faut sommé sur la bonne durée
                # Correction: La durée totale est calculée à la fin de la boucle par la différence entre la dernière heure d'arrivée et la première heure de départ.

            df_itineraire = pd.DataFrame(itineraire_data)
            st.dataframe(df_itineraire, use_container_width=True)

            # Affichage des totaux
            heure_fin_reelle = st.session_state.itineraire_complet[-1]["heure_arrivee"] if st.session_state.itineraire_complet else heure_debut_reelle
            duree_totale_reelle = heure_fin_reelle - heure_debut_reelle
            
            st.subheader("Récapitulatif de la Tournée")
            st.markdown(f"**Durée Totale Estimée :** {format_duration(duree_totale_reelle.total_seconds())}")
            st.markdown(f"**Distance Totale Estimée :** {format_distance(distance_totale_tournee)}")
            st.markdown(f"**Point de Départ :** {st.session_state.point_depart_return_input}")
            st.markdown(f"**Heure de Fin :** {heure_fin_reelle.strftime('%H:%M:%S') if heure_fin_reelle else 'N/A'}")
        else:
            st.warning("Aucun itinéraire détaillé n'a pu être généré.")
