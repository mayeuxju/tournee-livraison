import googlemaps
from datetime import datetime, timedelta
import random # Utilisé pour le test initial, pas pour la logique principale
import os # Pour potentiellement lire la clé API depuis l'environnement

# --- Configuration ---
# Assurez-vous d'avoir votre clé API Google Maps
# Idéalement, mettez-la dans une variable d'environnement pour des raisons de sécurité
# Exemple : export GOOGLE_MAPS_API_KEY='VOTRE_CLE_API'
# Si non trouvée, vous pouvez la coller directement ici, mais ce n'est pas recommandé
API_KEY = os.environ.get('AIzaSyA31LqMOI4B-99NCUSf1nPnpSwcWjqga4U', 'AIzaSyA31LqMOI4B-99NCUSf1nPnpSwcWjqga4U') # Remplacez si vous ne mettez pas de variable d'env
if API_KEY == 'AIzaSyA31LqMOI4B-99NCUSf1nPnpSwcWjqga4U':
    print("ATTENTION : Clé API Google Maps non configurée. L'application ne fonctionnera pas.")

gmaps = googlemaps.Client(key=API_KEY)

# --- Modèle de Données des Clients ---
class Client:
    def __init__(self, nom, adresse, type_arret, duree_visite_min=15, contrainte_horaire_debut=None, contrainte_horaire_fin=None, inclure_dans_aller_meme_si_ramasse=False):
        self.nom = nom
        self.adresse = adresse
        self.type_arret = type_arret # 'Livraison' ou 'Ramasse'
        self.duree_visite_min = duree_visite_min # Durée estimée de l'arrêt en minutes
        self.contrainte_horaire_debut = contrainte_horaire_debut # datetime.time ou None
        self.contrainte_horaire_fin = contrainte_horaire_fin # datetime.time ou None
        # Nouvelle option : traiter une ramasse comme une livraison pour le flux "aller"
        self.inclure_dans_aller_meme_si_ramasse = inclure_dans_aller_meme_si_ramasse

    def __repr__(self):
        return f"Client(nom='{self.nom}', type='{self.type_arret}')"

    def afficher_details(self):
        """Retourne une chaîne formatée pour l'affichage des détails du client."""
        details = f"{self.nom}\n{self.adresse}\n"
        details += f"Type : {self.type_arret}\n"
        details += f"⏱️ Durée : {self.duree_visite_min} min\n"
        if self.contrainte_horaire_debut and self.contrainte_horaire_fin:
            details += f"⏰ Horaire : {self.contrainte_horaire_debut.strftime('%H:%M')} - {self.contrainte_horaire_fin.strftime('%H:%M')}\n"
        if self.type_arret == 'Ramasse' and self.inclure_dans_aller_meme_si_ramasse:
            details += "➡️ Inclure dans l'aller\n"
        return details

# --- Fonctions Utilitaires ---

def get_coords(adresse):
    """Récupère les coordonnées géographiques d'une adresse."""
    try:
        geocode_result = gmaps.geocode(adresse)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return (location['lat'], location['lng'])
        return None
    except Exception as e:
        print(f"Erreur lors de la géocodification de {adresse}: {e}")
        return None

def get_travel_time(origin, destination, departure_time=None):
    """
    Récupère le temps de trajet estimé entre deux points (en secondes).
    Si departure_time est fourni, utilise les conditions de trafic actuelles ou futures.
    """
    try:
        # Si c'est un objet Client, on prend son adresse, sinon on suppose que c'est une adresse string ou des coords
        if isinstance(origin, Client): origin = origin.adresse
        if isinstance(destination, Client): destination = destination.adresse

        # googlemaps expects strings for addresses, or tuples for lat/lng
        if not isinstance(origin, str) and not (isinstance(origin, tuple) and len(origin) == 2):
            print(f"Erreur: Origine invalide pour get_travel_time: {origin}")
            return None
        if not isinstance(destination, str) and not (isinstance(destination, tuple) and len(destination) == 2):
            print(f"Erreur: Destination invalide pour get_travel_time: {destination}")
            return None

        # Si departure_time est None, on utilise le trafic en temps réel (ou le plus rapide si pas dispo)
        # Sinon, on utilise les conditions de trafic pour l'heure spécifiée.
        directions_result = gmaps.directions(origin,
                                             destination,
                                             mode="driving",
                                             departure_time=departure_time) # departure_time peut être un timestamp Unix ou un objet datetime

        if directions_result and 'legs' in directions_result[0] and directions_result[0]['legs']:
            return directions_result[0]['legs'][0]['duration']['value'] # Valeur en secondes
        return None
    except Exception as e:
        print(f"Erreur lors de la récupération du temps de trajet: {e}")
        # print(f"Origin: {origin}, Destination: {destination}, Departure Time: {departure_time}") # Debugging
        return None

def format_duration_seconds(seconds):
    """Formate une durée en secondes en HH:MM:SS ou MM:SS."""
    if seconds is None:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def calculate_route_details(clients, start_datetime=None):
    """
    Calcule le temps de trajet et les temps d'arrivée/départ pour une séquence de clients.
    Retourne une liste d'arrêts avec leurs détails (heure d'arrivée, départ, etc.) et le temps total.
    """
    if not clients:
        return [], timedelta(0)

    route_details = []
    current_time = start_datetime
    total_travel_duration_seconds = 0

    # Pré-calculer les coordonnées pour éviter des appels API répétés
    coords_cache = {client.adresse: get_coords(client.adresse) for client in clients}
    if None in coords_cache.values():
        print("ERREUR : Impossible de géocoder tous les points. Vérifiez les adresses.")
        # Potentiellement, on pourrait arrêter ici ou continuer avec les points géocodés
        # Pour l'instant, on continue, mais les temps de trajet pourraient être erronés
        # On va plutôt essayer de récupérer le temps de trajet directement avec les adresses string pour la tolérance de l'API
        pass # On va laisser le get_travel_time gérer les adresses strings

    # On définit une heure de départ pour le calcul du trafic si start_datetime est fourni
    # Si start_datetime est une date sans heure, on prend 8h du matin par défaut
    departure_time_for_traffic = start_datetime
    if isinstance(departure_time_for_traffic, datetime) and departure_time_for_traffic.time() == datetime.min.time():
         departure_time_for_traffic = departure_time_for_traffic.replace(hour=8, minute=0, second=0)


    for i in range(len(clients)):
        current_client = clients[i]
        current_adresse = current_client.adresse # Utiliser l'adresse string ici

        # 1. Temps d'arrivée au client
        if i == 0:
            # C'est le premier arrêt, il part du dépôt à current_time
            heure_arrivee = current_time
        else:
            previous_client_departure_time = route_details[-1]['heure_depart']
            # Récupérer le temps de trajet depuis le DÉPART du client précédent
            # Si on a calculé les coords, on pourrait utiliser ça, sinon on utilise les adresses
            travel_time_seconds = get_travel_time(clients[i-1].adresse, current_adresse, departure_time=previous_client_departure_time)
            if travel_time_seconds is None:
                print(f"AVERTISSEMENT : Temps de trajet non trouvé entre {clients[i-1].nom} et {current_client.nom}. Utilisation d'un temps par défaut ou ignorer.")
                travel_time_seconds = 1200 # Valeur par défaut de 20 minutes si erreur

            total_travel_duration_seconds += travel_time_seconds
            heure_arrivee = previous_client_departure_time + timedelta(seconds=travel_time_seconds)

        # 2. Gestion des contraintes horaires et de la durée de visite
        heure_depart_effective = heure_arrivee
        attente = timedelta(0)

        # Vérifier la contrainte horaire
        if current_client.contrainte_horaire_debut and current_client.contrainte_horaire_fin:
            # S'assurer que l'heure d'arrivée est au moins l'heure de début
            if heure_arrivee.time() < current_client.contrainte_horaire_debut:
                # Calculer le temps d'attente
                attente_heure_debut = datetime.combine(heure_arrivee.date(), current_client.contrainte_horaire_debut)
                attente = attente_heure_debut - heure_arrivee
                heure_depart_effective = attente_heure_debut # Le départ sera après l'attente

        # S'assurer que le départ n'est pas APRÈS la fin de la fenêtre horaire (sauf si l'attente est obligatoire)
        # On ne va pas forcer le départ avant la fin, mais on le note si c'est le cas
        # La logique d'optimisation plus poussée gérera la réorganisation si l'attente est trop longue.
        # Pour le calcul de base, on laisse juste l'arrivée et on ajoute le temps de visite
        # Le temps de visite commence APRES l'attente (si il y en a)
        temps_visite_total = timedelta(minutes=current_client.duree_visite_min)
        heure_depart_effective = heure_depart_effective + temps_visite_total

        # 3. Calculer l'heure de départ finale
        # Le départ est l'heure d'arrivée + attente (si il y a) + temps de visite
        heure_depart_finale = heure_depart_effective # C'est déjà heure_arrivee + attente + duree_visite

        # Si on a une contrainte horaire de fin, il faut s'assurer qu'on ne commence pas la visite APRES la fin
        # Si heure_arrivee est APRÈS contrainte_horaire_fin, cela signifie qu'on est en retard.
        # Le calcul actuel gère l'attente au début, mais pas le fait de finir après la fenêtre.
        # Pour l'instant, on se concentre sur le début de la fenêtre.

        route_details.append({
            'client': current_client,
            'heure_arrivee': heure_arrivee,
            'attente': attente,
            'heure_depart_visite': heure_arrivee + attente, # Quand on commence la visite
            'heure_depart': heure_depart_finale, # Quand on quitte le point
            'temps_trajet_precedent_sec': travel_time_seconds if i > 0 else 0
        })

        current_time = heure_depart_finale # Prépare pour le prochain calcul

    # Calculer le temps total de la tournée (trajet + visites)
    total_visit_duration = timedelta(0)
    for detail in route_details:
        total_visit_duration += timedelta(minutes=detail['client'].duree_visite_min)
        total_visit_duration += detail['attente'] # Ajouter l'attente comme du temps "perdu" dans la tournée

    total_duration = timedelta(seconds=total_travel_duration_seconds) + total_visit_duration

    return route_details, total_duration

def optimiser_tournee(clients_input, start_datetime_str="08:00"):
    """
    Fonction principale d'optimisation de la tournée.
    Prend une liste d'objets Client et une heure de départ.
    Retourne la tournée optimisée et les détails calculés.
    """
    if not clients_input:
        return [], timedelta(0)

    # Définir la date du jour pour les calculs de contraintes horaires
    today = datetime.now().date()
    start_hour, start_minute = map(int, start_datetime_str.split(':'))
    start_datetime = datetime.combine(today, datetime.time(start_hour, start_minute))

    # Séparer les livraisons des ramasses
    livraisons = [c for c in clients_input if c.type_arret == 'Livraison']
    ramasses = [c for c in clients_input if c.type_arret == 'Ramasse']

    # Identifier les ramasses à traiter comme des livraisons (dans le flux "aller")
    ramasses_comme_livraisons = [r for r in ramasses if r.inclure_dans_aller_meme_si_ramasse]
    ramasses_restantes = [r for r in ramasses if not r.inclure_dans_aller_meme_si_ramasse]

    # Construire la séquence de livraisons (incluant les ramasses "déguisées")
    # On les mélange pour l'instant, la vraie optimisation vient après
    flux_aller = livraisons + ramasses_comme_livraisons
    flux_retour = ramasses_restantes

    # --- Logique d'Optimisation "Logique Chauffeur" + Priorité Horaire ---
    # 1. Ordre de base : Tout livrer d'abord, puis tout ramasser.
    #    Si il y a des ramasses incluses dans l'aller, elles viennent avec les livraisons.

    # 2. Calculer l'ordre des livraisons (flux_aller) en essayant de minimiser l'attente
    #    On va faire une heuristique simple :
    #    a. Tri initial : Les points avec contrainte horaire la plus proche en premier.
    #    b. Réorganisation itérative pour minimiser l'attente.

    def order_clients_for_flow(clients_to_order, start_time_for_flow):
        """
        Trie une liste de clients pour un flux donné (aller ou retour)
        en essayant de minimiser l'attente aux contraintes horaires.
        Retourne la liste triée.
        """
        if not clients_to_order:
            return []

        # Liste de travail
        current_clients = list(clients_to_order)
        ordered_clients = []
        current_flow_time = start_time_for_flow

        # Boucle principale pour construire l'ordre
        while current_clients:
            best_next_client = None
            min_total_time_if_selected = float('inf') # Temps total de la tournée si ce client est choisi MAINTENANT
            earliest_possible_arrival = None # Heure d'arrivée si ce client est choisi MAINTENANT

            for i, client in enumerate(current_clients):
                # Calculer l'heure d'arrivée si ce client est le PROCHAIN
                if ordered_clients:
                    # Temps de trajet depuis le dernier client ordonné
                    travel_time_sec = get_travel_time(ordered_clients[-1].adresse, client.adresse, departure_time=ordered_clients[-1].heure_depart)
                    if travel_time_sec is None: travel_time_sec = 1200 # Fallback
                    potential_arrival_time = ordered_clients[-1].heure_depart + timedelta(seconds=travel_time_sec)
                else:
                    # C'est le premier client du flux, arrivée au départ du flux
                    potential_arrival_time = current_flow_time

                # Calculer l'attente potentielle pour ce client
                potential_wait_time = timedelta(0)
                if client.contrainte_horaire_debut:
                    arrival_time_obj = potential_arrival_time.time()
                    start_window_obj = client.contrainte_horaire_debut
                    # S'assurer que l'arrivée est APRÈS le début de la fenêtre
                    if arrival_time_obj < start_window_obj:
                        wait_until = datetime.combine(potential_arrival_time.date(), start_window_obj)
                        potential_wait_time = wait_until - potential_arrival_time

                # Temps total depuis le début du flux si ce client est choisi
                # On prend le temps de départ du dernier client ordonné + temps de trajet + attente + durée visite
                time_after_visit = potential_arrival_time + potential_wait_time + timedelta(minutes=client.duree_visite_min)

                # On cherche le client qui permet de finir LE PLUS TÔT dans le flux
                # C'est une heuristique simple, d'autres stratégies sont possibles (ex: celui qui minimise l'attente SEULEMENT)
                if time_after_visit < datetime.now().replace(hour=23, minute=59): # Eviter les valeurs infinies ou trop lointaines
                     if time_after_visit < min_total_time_if_selected:
                        min_total_time_if_selected = time_after_visit
                        best_next_client = client
                        earliest_possible_arrival = potential_arrival_time # Garder l'heure d'arrivée pour le calcul final

            if best_next_client:
                # Calculer les détails finaux pour le meilleur client sélectionné
                # Il faut réutiliser la logique de calculate_route_details mais juste pour CE client et son prédécesseur
                # On peut le faire en simulant un appel à calculate_route_details sur une petite liste
                simulated_clients = [c for c in ordered_clients] + [best_next_client]
                # Le temps de départ du PRECEDENT client doit être le vrai heure_depart
                if ordered_clients:
                    simulated_clients[-2].heure_depart = ordered_clients[-1].heure_depart # On a besoin de l'heure de départ du dernier client déjà ordonné

                # On a besoin de l'heure de départ du client précédent pour calculer le temps de trajet
                if len(ordered_clients) > 0:
                    prev_client_depart_time = ordered_clients[-1].heure_depart
                else:
                    prev_client_depart_time = current_flow_time # Si c'est le premier

                # Calculer l'heure d'arrivée pour ce client
                if len(ordered_clients) > 0:
                    travel_time_sec = get_travel_time(ordered_clients[-1].adresse, best_next_client.adresse, departure_time=prev_client_depart_time)
                    if travel_time_sec is None: travel_time_sec = 1200
                    actual_arrival_time = prev_client_depart_time + timedelta(seconds=travel_time_sec)
                else:
                    actual_arrival_time = current_flow_time

                # Calculer l'attente pour ce client
                actual_wait_time = timedelta(0)
                if best_next_client.contrainte_horaire_debut:
                    arrival_time_obj = actual_arrival_time.time()
                    start_window_obj = best_next_client.contrainte_horaire_debut
                    if arrival_time_obj < start_window_obj:
                        wait_until = datetime.combine(actual_arrival_time.date(), start_window_obj)
                        actual_wait_time = wait_until - actual_arrival_time

                # Calculer l'heure de départ
                final_departure_time = actual_arrival_time + actual_wait_time + timedelta(minutes=best_next_client.duree_visite_min)

                # Mettre à jour l'objet client pour stocker les temps calculés
                best_next_client.heure_arrivee = actual_arrival_time
                best_next_client.attente = actual_wait_time
                best_next_client.heure_depart_visite = actual_arrival_time + actual_wait_time
                best_next_client.heure_depart = final_departure_time
                # Si c'est le premier client, le temps de trajet précédent est 0
                best_next_client.temps_trajet_precedent_sec = get_travel_time(ordered_clients[-1].adresse, best_next_client.adresse, departure_time=prev_client_depart_time) if ordered_clients else 0

                ordered_clients.append(best_next_client)
                current_clients.remove(best_next_client)
                current_flow_time = final_departure_time # Le temps de départ de ce client devient le temps de départ du flux pour le prochain

            else:
                # Si aucun client ne peut être sélectionné (ex: tous déjà dans ordered_clients),
                # ou s'il y a une erreur, on sort pour éviter une boucle infinie.
                print("ERREUR : Impossible de sélectionner le prochain client. Arrêt de l'optimisation de ce flux.")
                break

        return ordered_clients

    # Ordonner le flux aller
    ordered_flux_aller = order_clients_for_flow(flux_aller, start_datetime)

    # Ordonner le flux retour (les ramasses restantes)
    # Le départ du flux retour est le moment où le dernier client de l'aller est livré.
    start_time_retour = start_datetime # Si le flux aller est vide
    if ordered_flux_aller:
        start_time_retour = ordered_flux_aller[-1].heure_depart # Heure de départ du dernier client de l'aller

    ordered_flux_retour = order_clients_for_flow(flux_retour, start_time_retour)

    # Combinaison finale des tours
    final_route = ordered_flux_aller + ordered_flux_retour

    # Recalculer tous les détails de la tournée complète
    # On utilise une fonction similaire à calculate_route_details, mais en s'assurant d'utiliser les objets Client mis à jour
    # pour les temps calculés si possible, ou en recalculant entièrement.
    # Le plus simple pour l'instant est de recalculer entièrement avec la séquence finale.
    # Mais il faut s'assurer que la fonction de calcul prend bien en compte les `heure_depart` des clients précédents
    # pour le `departure_time` dans `get_travel_time`.
    # C'est le rôle de calculate_route_details avec une start_datetime qui est le temps de départ du dépôt.

    # On réinitialise les temps calculés sur les objets pour la fonction de calcul finale
    for client in final_route:
        if hasattr(client, 'heure_arrivee'): del client.heure_arrivee
        if hasattr(client, 'attente'): del client.attente
        if hasattr(client, 'heure_depart_visite'): del client.heure_depart_visite
        if hasattr(client, 'heure_depart'): del client.heure_depart
        if hasattr(client, 'temps_trajet_precedent_sec'): del client.temps_trajet_precedent_sec


    final_route_details, total_duration = calculate_route_details(final_route, start_datetime)

    # Retourner les objets Client mis à jour avec les temps calculés, et la durée totale
    # Les objets `client` dans `final_route_details` sont les mêmes que ceux dans `final_route`, donc ils ont été mis à jour.
    return final_route_details, total_duration

# --- Interface Utilisateur (Exemple basique avec input/print) ---

def main():
    print("--- Optimiseur de Tournée V2 ---")
    print("Entrez les détails des arrêts.")
    print("Tapez 'fin' pour le nom du client pour terminer la saisie.")

    clients_saisie = []
    type_arret_options = ['Livraison', 'Ramasse']

    while True:
        nom_client = input(f"Nom du client (ou 'fin' pour terminer) : ").strip()
        if nom_client.lower() == 'fin':
            break

        adresse = input(f"Adresse complète pour '{nom_client}' : ").strip()

        while True:
            type_arret = input(f"Type d'arrêt pour '{nom_client}' (Livraison / Ramasse) : ").strip()
            if type_arret in type_arret_options:
                break
            else:
                print("Veuillez entrer 'Livraison' ou 'Ramasse'.")

        duree_visite_min = 15 # Valeur par défaut
        try:
            duree_str = input(f"Durée de visite estimée en minutes pour '{nom_client}' (laisser vide pour {duree_visite_min} min) : ").strip()
            if duree_str:
                duree_visite_min = int(duree_str)
        except ValueError:
            print("Durée invalide, utilisation de la valeur par défaut.")

        contrainte_horaire_debut = None
        contrainte_horaire_fin = None
        while True:
            choix_horaire = input(f"Ce client a-t-il une contrainte horaire ? (oui/non) : ").strip().lower()
            if choix_horaire == 'oui':
                while True:
                    h_debut_str = input(f"Heure de début de la fenêtre horaire (format HH:MM, ex: 09:30) : ").strip()
                    try:
                        h_debut = datetime.strptime(h_debut_str, '%H:%M').time()
                        break
                    except ValueError:
                        print("Format d'heure invalide. Veuillez utiliser HH:MM.")
                while True:
                    h_fin_str = input(f"Heure de fin de la fenêtre horaire (format HH:MM, ex: 17:00) : ").strip()
                    try:
                        h_fin = datetime.strptime(h_fin_str, '%H:%M').time()
                        if h_fin > h_debut: # Vérification simple que la fin est après le début
                            contrainte_horaire_debut = h_debut
                            contrainte_horaire_fin = h_fin
                            break
                        else:
                            print("L'heure de fin doit être après l'heure de début.")
                    except ValueError:
                        print("Format d'heure invalide. Veuillez utiliser HH:MM.")
                break # Sortir de la boucle choix_horaire
            elif choix_horaire == 'non':
                break # Sortir de la boucle choix_horaire
            else:
                print("Veuillez répondre par 'oui' ou 'non'.")

        inclure_dans_aller = False
        if type_arret == 'Ramasse':
            while True:
                choix_aller = input(f"['{nom_client}'] est une ramasse. Voulez-vous l'inclure dans le voyage 'aller' comme une livraison ? (oui/non) : ").strip().lower()
                if choix_aller == 'oui':
                    inclure_dans_aller = True
                    break
                elif choix_aller == 'non':
                    break
                else:
                    print("Veuillez répondre par 'oui' ou 'non'.")

        client = Client(nom_client, adresse, type_arret, duree_visite_min, contrainte_horaire_debut, contrainte_horaire_fin, inclure_dans_aller)
        clients_saisie.append(client)
        print("-" * 20) # Séparateur

    if not clients_saisie:
        print("Aucun client saisi. Fin du programme.")
        return

    start_datetime_str = input("Entrez l'heure de départ de la tournée (format HH:MM, ex: 08:00) : ").strip()
    try:
        datetime.strptime(start_datetime_str, '%H:%M')
    except ValueError:
        print("Format d'heure de départ invalide. Utilisation de 08:00 par défaut.")
        start_datetime_str = "08:00"

    print("\n--- Optimisation de la tournée en cours ---")
    print("Veuillez patienter pendant le calcul des temps de trajet...")

    # Appel de la fonction d'optimisation
    route_details, total_duration = optimiser_tournee(clients_saisie, start_datetime_str)

    print("\n--- Résultat de l'Optimisation ---")
    if not route_details:
        print("Impossible de calculer la tournée.")
        return

    print(f"Heure de départ : {start_datetime_str}")
    print(f"Durée totale estimée de la tournée : {format_duration_seconds(total_duration.total_seconds())}")
    print("\nOrdre des arrêts optimisé :")
    print("=" * 40)

    for i, arret in enumerate(route_details):
        print(f"Arrêt {i+1}:")
        print(arret['client'].afficher_details())
        print(f"  Heure d'arrivée : {arret['heure_arrivee'].strftime('%H:%M:%S')}")
        if arret['attente'] > timedelta(0):
            print(f"  Temps d'attente : {format_duration_seconds(arret['attente'].total_seconds())}")
        print(f"  Heure de départ : {arret['heure_depart'].strftime('%H:%M:%S')}")
        if i < len(route_details) - 1:
            # On affiche le temps de trajet vers le prochain arrêt
            next_arret = route_details[i+1]
            # Pour obtenir le temps de trajet réel vers le prochain, il faut le recalculer
            # car le `temps_trajet_precedent_sec` stocké est celui utilisé lors de l'ordonnancement.
            # Ce n'est pas toujours le temps de trajet EXACT si la fenêtre horaire a forcé un départ plus tardif.
            # La façon la plus simple est de prendre le `heure_arrivee` du prochain et de la soustraire du `heure_depart` actuel.
            if next_arret['heure_arrivee'] and arret['heure_depart']:
                 actual_travel_time = next_arret['heure_arrivee'] - arret['heure_depart']
                 print(f"  Temps de trajet vers '{next_arret['client'].nom}' : {format_duration_seconds(actual_travel_time.total_seconds())}")

        print("-" * 20)

    print("=" * 40)
    print("Fin de la tournée.")

if __name__ == "__main__":
    main()
