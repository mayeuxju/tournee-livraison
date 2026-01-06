import streamlit as st
import googlemaps
from datetime import datetime, timedelta
import heapq # Pour l'algorithme de recherche de plus court chemin, potentiellement utile

# --- Importation de la clé API secrète ---
try:
    from secrets import GOOGLE_API_KEY
except ImportError:
    st.error("Le fichier 'secrets.py' n'a pas été trouvé ou n'est pas correctement configuré.")
    st.error("Veuillez créer un fichier 'secrets.py' avec votre clé GOOGLE_API_KEY.")
    st.stop()

if GOOGLE_API_KEY == "VOTRE_CLE_API_SECRETE_ICI" or not GOOGLE_API_KEY:
    st.error("Veuillez remplacer 'VOTRE_CLE_API_SECRETE_ICI' par votre vraie clé API dans le fichier 'secrets.py'.")
    st.stop()

gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

# --- Constantes ---
TEMPS_DE_MARCHE_PAR_DEFAUT = 5 # minutes par arrêt, pour le trajet entre deux points
SEUIL_ATTENTE_OPTIMALE = timedelta(minutes=15) # Seuil pour déclencher la réorganisation pour minimiser l'attente

# --- Fonctions Utilitaires ---

def obtenir_infos_lieu(adresse):
    """Récupère les informations de base d'un lieu via l'API Google Places."""
    try:
        places_result = gmaps.places(query=adresse, type="establishment")
        if places_result.get("results"):
            place_id = places_result["results"][0]["place_id"]
            details = gmaps.place(place_id=place_id, fields=["name", "formatted_address", "opening_hours"])
            # Si on trouve un nom plus précis (ex: le nom du magasin), on le préfère
            nom_lieu = details.get("result", {}).get("name", adresse)
            return nom_lieu
        return adresse # Retourne l'adresse si aucun nom spécifique trouvé
    except Exception as e:
        st.warning(f"Erreur lors de la récupération des détails pour {adresse}: {e}")
        return adresse # Retourne l'adresse en cas d'erreur

def calculer_duree_trajet(origine, destination, depart_heure=None):
    """Calcule la durée du trajet entre deux points en tenant compte du trafic si depart_heure est fourni."""
    try:
        if depart_heure:
            now = depart_heure
        else:
            now = datetime.now() # Utiliser l'heure actuelle si pas spécifiée

        directions_result = gmaps.directions(
            origine,
            destination,
            mode="driving",
            departure_time=now # Important pour le trafic en temps réel/prévu
        )

        if directions_result and directions_result[0].get("legs"):
            leg = directions_result[0]["legs"][0]
            duree_secondes = leg["duration_in_traffic"]["value"] if "duration_in_traffic" in leg else leg["duration"]["value"]
            return timedelta(seconds=duree_secondes)
        else:
            st.warning(f"Impossible de calculer le trajet de {origine} à {destination}.")
            return timedelta(minutes=30) # Valeur par défaut raisonnable en cas d'échec
    except Exception as e:
        st.warning(f"Erreur API Google Maps pour trajet {origine} -> {destination}: {e}")
        return timedelta(minutes=30) # Valeur par défaut en cas d'erreur API

def formater_duree(delta):
    """Formate un timedelta en HH:MM:SS ou MM:SS."""
    total_secondes = int(delta.total_seconds())
    heures = total_secondes // 3600
    minutes = (total_secondes % 3600) // 60
    secondes = total_secondes % 60
    if heures > 0:
        return f"{heures:02d}:{minutes:02d}:{secondes:02d}"
    else:
        return f"{minutes:02d}:{secondes:02d}"

# --- Modèles de données ---
class PointInteret:
    def __init__(self, nom, adresse, type_point, contraintes=None, id_unique=None):
        self.id_unique = id_unique or f"{nom}_{adresse}" # Génère un ID unique
        self.nom = nom
        self.adresse = adresse
        self.type_point = type_point # "Livraison" ou "Ramasse"
        self.contraintes = contraintes or {}
        self.temps_service = self.contraintes.get("temps_service", timedelta(minutes=TEMPS_DE_MARCHE_PAR_DEFAUT))
        self.fenetre_horaire = self.contraintes.get("fenetre_horaire") # Tuple (debut, fin) en minutes depuis minuit
        self.inclure_dans_aller = self.contraintes.get("inclure_dans_aller", False) # Pour les ramasses spécifiques

    def __repr__(self):
        return f"PointInteret(nom='{self.nom}', type='{self.type_point}', id='{self.id_unique}')"

    def est_livraison(self):
        return self.type_point == "Livraison"

    def est_ramasse(self):
        return self.type_point == "Ramasse"

    def get_fenetre_horaire_str(self):
        if self.fenetre_horaire:
            debut_h = self.fenetre_horaire[0] // 60
            debut_m = self.fenetre_horaire[0] % 60
            fin_h = self.fenetre_horaire[1] // 60
            fin_m = self.fenetre_horaire[1] % 60
            return f"{debut_h:02d}:{debut_m:02d} - {fin_h:02d}:{fin_m:02d}"
        return ""

# --- Logique d'Optimisation ---

def optimiser_tournee(points_depart, points_arrivee, depart_adresse_initiale, heure_debut_tournee):
    """
    Optimise la tournée en respectant les livraisons d'abord, puis les ramasses,
    en intégrant la priorité horaire et les ramasses spécifiques.

    Args:
        points_depart (list[PointInteret]): Liste des points de livraison.
        points_arrivee (list[PointInteret]): Liste des points de ramasse.
        depart_adresse_initiale (str): Adresse de départ du véhicule.
        heure_debut_tournee (datetime): Heure de début de la tournée.

    Returns:
        tuple: (liste_arrets_ordonnee, total_duree_estimation)
    """

    # Séparation des points en fonction du type et de l'option "inclure_dans_aller"
    livraisons_finales = [p for p in points_depart if p.est_livraison()]
    ramasses_retour_normal = [p for p in points_arrivee if p.est_ramasse() and not p.inclure_dans_aller]
    ramasses_retour_speciales = [p for p in points_arrivee if p.est_ramasse() and p.inclure_dans_aller]

    # L'ordre "idéal" est: toutes les livraisons (normales + spéciales), puis les ramasses de retour normales.
    # L'algorithme actuel ne réorganise pas les livraisons entre elles, il les prend dans l'ordre fourni.
    # On va construire la partie "aller" en ajoutant les ramasses spéciales dedans.
    
    # Fusionne les livraisons et les ramasses spéciales pour la phase "aller"
    points_aller = livraisons_finales + ramasses_retour_speciales
    points_retour = ramasses_retour_normal # Ces points ne seront visités qu'après la fin des livraisons et ramasses spéciales

    # --- Calcul de la partie "Aller" ---
    tournee_aller_optimisee = []
    heure_actuelle = heure_debut_tournee
    adresse_actuelle = depart_adresse_initiale
    
    # Boucle principale pour ordonnancer les points de l'aller
    # C'est ici que l'on essaie d'optimiser pour l'heure et on intègre les ramasses spéciales
    
    # 1. Pré-calculer les temps d'arrivée théoriques pour chaque point de l'aller
    points_aller_avec_temps = []
    temp_heure = heure_debut_tournee
    temp_adresse = depart_adresse_initiale
    for point in points_aller:
        duree_trajet = calculer_duree_trajet(temp_adresse, point.adresse, temp_heure)
        temp_heure += duree_trajet
        
        # Gestion des contraintes horaires et temps de service
        attente = timedelta()
        heure_arrivee_prevue = temp_heure
        
        if point.fenetre_horaire:
            debut_fenetre_minutes = point.fenetre_horaire[0]
            fin_fenetre_minutes = point.fenetre_horaire[1]
            
            # Convertir heure_arrivee_prevue en minutes depuis minuit pour comparaison
            arrivee_minutes = heure_arrivee_prevue.hour * 60 + heure_arrivee_prevue.minute
            
            if arrivee_minutes < debut_fenetre_minutes:
                attente = timedelta(minutes=(debut_fenetre_minutes - arrivee_minutes))
                heure_actuelle_pour_point = heure_arrivee_prevue + attente
            else:
                heure_actuelle_pour_point = heure_arrivee_prevue
            
            if heure_actuelle_pour_point.hour * 60 + heure_actuelle_pour_point.minute > fin_fenetre_minutes:
                # On dépasse la fenêtre, ce scénario est plus complexe. Pour l'instant, on marque comme non optimal
                # ou on peut décider de ne pas le mettre dans l'aller s'il y a un risque.
                # Pour simplifier, on assume que c'est possible mais cela peut nécessiter une réorganisation plus poussée
                pass # Pour l'instant, on continue, le système pourrait devoir gérer un dépassement

        else:
            heure_actuelle_pour_point = heure_arrivee_prevue

        heure_actuelle_pour_point += point.temps_service # Ajout du temps de service

        points_aller_avec_temps.append({
            "point": point,
            "heure_arrivee_prevue": heure_arrivee_prevue,
            "attente": attente,
            "heure_depart_reel": heure_actuelle_pour_point,
            "duree_trajet_precedente": duree_trajet
        })
        temp_adresse = point.adresse
        
    # --- Stratégie d'optimisation pour l'attente ---
    # Si l'attente totale est trop grande, on pourrait essayer de réordonner les livraisons/ramasses spéciales
    # Pour cette version, on garde l'ordre initial des livraisons et on insère les ramasses spéciales à la fin des livraisons.
    # L'optimisation "moins d'attente" est complexe et impliquerait un algorithme de plus court chemin plus sophistiqué.
    # Pour l'instant, on privilégie la structure : Livraisons -> Ramasses Spéciales (si incluses) -> Ramasses Normales.
    
    # Construction de la tournée finale avec les temps calculés
    tournee_optimisee = []
    heure_courante_calcul = heure_debut_tournee
    adresse_courante_calcul = depart_adresse_initiale
    
    # Points à visiter dans l'ordre : Livraisons -> Ramasses Spéciales
    points_a_visiter_aller = livraisons_finales + ramasses_retour_speciales

    for point in points_a_visiter_aller:
        duree_trajet = calculer_duree_trajet(adresse_courante_calcul, point.adresse, heure_courante_calcul)
        heure_arrivee_reel = heure_courante_calcul + duree_trajet
        
        attente = timedelta()
        heure_depart_reelle = heure_arrivee_reel

        if point.fenetre_horaire:
            debut_fenetre_minutes = point.fenetre_horaire[0]
            fin_fenetre_minutes = point.fenetre_horaire[1]
            
            # Convertir heure_arrivee_reel en minutes depuis minuit pour comparaison
            arrivee_reel_minutes = heure_arrivee_reel.hour * 60 + heure_arrivee_reel.minute
            
            if arrivee_reel_minutes < debut_fenetre_minutes:
                attente = timedelta(minutes=(debut_fenetre_minutes - arrivee_reel_minutes))
                heure_depart_reelle = heure_arrivee_reel + attente
            else:
                heure_depart_reelle = heure_arrivee_reel
            
            # Vérification si on dépasse la fin de la fenêtre.
            # Si c'est le cas, on pourrait décider de ne pas inclure ce point dans l'aller,
            # ou le marquer comme une exception. Pour l'instant, on le laisse faire.
            if heure_depart_reelle.hour * 60 + heure_depart_reelle.minute > fin_fenetre_minutes:
                st.warning(f"L'arrivée à {point.nom} ({point.adresse}) dépasse la fenêtre horaire ({point.get_fenetre_horaire_str()}). L'heure de départ sera {heure_depart_reelle.strftime('%H:%M')}.")

        heure_depart_reelle += point.temps_service
        
        tournee_optimisee.append({
            "point": point,
            "heure_arrivee": heure_arrivee_reel,
            "attente": attente,
            "heure_depart": heure_depart_reelle,
            "duree_trajet_precedente": duree_trajet,
            "nom_lieu_specifique": obtenir_infos_lieu(point.adresse) # Récupère le nom plus précis si disponible
        })
        
        heure_courante_calcul = heure_depart_reelle
        adresse_courante_calcul = point.adresse

    # --- Calcul de la partie "Retour" (Ramasses normales) ---
    # Ces points ne sont visités qu'après la fin de la phase "aller"
    points_a_visiter_retour = ramasses_retour_normal

    for point in points_a_visiter_retour:
        duree_trajet = calculer_duree_trajet(adresse_courante_calcul, point.adresse, heure_courante_calcul)
        heure_arrivee_reel = heure_courante_calcul + duree_trajet
        
        attente = timedelta() # On suppose que les ramasses n'ont pas de fenêtre horaire stricte dans ce modèle
        heure_depart_reelle = heure_arrivee_reel
        
        # Pas de contrainte horaire ici pour les ramasses, mais on pourrait en ajouter.
        # On ajoute juste le temps de service.
        heure_depart_reelle += point.temps_service
        
        tournee_optimisee.append({
            "point": point,
            "heure_arrivee": heure_arrivee_reel,
            "attente": attente,
            "heure_depart": heure_depart_reelle,
            "duree_trajet_precedente": duree_trajet,
            "nom_lieu_specifique": obtenir_infos_lieu(point.adresse)
        })
        
        heure_courante_calcul = heure_depart_reelle
        adresse_courante_calcul = point.adresse

    # Calcul du total de la durée de la tournée
    duree_totale_estimee = heure_courante_calcul - heure_debut_tournee

    return tournee_optimisee, duree_totale_estimee

# --- Interface Streamlit ---

st.set_page_config(page_title="Optimiseur de Tournée", layout="wide")

st.title("🚗 Optimiseur de Tournée Intelligent")
st.markdown("Planifiez vos livraisons et ramasses de manière efficace.")

# --- Section Configuration ---
st.sidebar.header("Configuration Initiale")

# Adresse de départ et heure
depart_adresse_initiale = st.sidebar.text_input("Adresse de départ du véhicule :", "Rue du Rhône 1, Genève")
heure_debut_str = st.sidebar.text_input("Heure de début de la tournée (HH:MM) :", "08:00")
# Combiner date du jour et heure saisie
try:
    heure_debut_tournee_obj = datetime.combine(datetime.today(), datetime.strptime(heure_debut_str, "%H:%M").time())
except ValueError:
    st.sidebar.error("Format d'heure invalide. Veuillez utiliser HH:MM (ex: 08:00).")
    st.stop()

# Séparation des entrées pour les livraisons et les ramasses
st.header("Points de Passage")

# Utilisation de st.session_state pour persister les données des points
if 'points_data' not in st.session_state:
    st.session_state.points_data = {
        "livraisons": [],
        "ramasses": []
    }

# --- Zone d'ajout de Livraisons ---
st.subheader("Ajouter une Livraison")
with st.expander("Détails Livraison", expanded=False):
    nom_livraison = st.text_input("Nom du client (ex: Magasin X) :", key="nom_livraison_input")
    adresse_livraison = st.text_input("Adresse complète :", key="adresse_livraison_input")
    
    # Fenêtre horaire pour les livraisons
    st.write("Fenêtre horaire de livraison (optionnel) :")
    col_debut_h, col_debut_m, col_fin_h, col_fin_m = st.columns(4)
    debut_h = col_debut_h.number_input("Début H", min_value=0, max_value=23, value=9, key="debut_h_livraison")
    debut_m = col_debut_m.number_input("Début M", min_value=0, max_value=59, value=30, key="debut_m_livraison")
    fin_h = col_fin_h.number_input("Fin H", min_value=0, max_value=23, value=11, key="fin_h_livraison")
    fin_m = col_fin_m.number_input("Fin M", min_value=0, max_value=59, value=30, key="fin_m_livraison")
    
    temps_service_livraison_min = st.number_input("Temps de service estimé (minutes) :", min_value=1, value=10, key="temps_service_livraison")

    if st.button("Ajouter cette Livraison", key="add_livraison_btn"):
        if nom_livraison and adresse_livraison:
            fenetre_horaire_minutes = (debut_h * 60 + debut_m, fin_h * 60 + fin_m)
            if fenetre_horaire_minutes[0] >= fenetre_horaire_minutes[1]:
                st.warning("L'heure de début de la fenêtre horaire doit être avant l'heure de fin.")
            else:
                nouvelle_livraison = PointInteret(
                    nom=nom_livraison,
                    adresse=adresse_livraison,
                    type_point="Livraison",
                    contraintes={
                        "temps_service": timedelta(minutes=temps_service_livraison_min),
                        "fenetre_horaire": fenetre_horaire_minutes
                    }
                )
                st.session_state.points_data["livraisons"].append(nouvelle_livraison)
                # Vider les champs pour la prochaine saisie
                st.session_state.nom_livraison_input = ""
                st.session_state.adresse_livraison_input = ""
                st.rerun() # Rafraîchir pour afficher le nouveau point et vider les inputs
        else:
            st.warning("Veuillez renseigner le nom et l'adresse de la livraison.")

# --- Zone d'ajout de Ramasses ---
st.subheader("Ajouter une Ramasse")
with st.expander("Détails Ramasse", expanded=False):
    nom_ramasse = st.text_input("Nom du client (ex: Entrepôt Y) :", key="nom_ramasse_input")
    adresse_ramasse = st.text_input("Adresse complète :", key="adresse_ramasse_input")
    
    # Option spéciale: Inclure dans l'aller
    inclure_dans_aller_ramasse = st.checkbox("Inclure dans l'aller (traiter comme une livraison pour le calcul du trajet aller) ?", key="inclure_dans_aller_checkbox")
    
    # Fenêtre horaire pour les ramasses (moins courant mais possible)
    st.write("Fenêtre horaire de ramasse (optionnel) :")
    col_debut_h_r, col_debut_m_r, col_fin_h_r, col_fin_m_r = st.columns(4)
    debut_h_r = col_debut_h_r.number_input("Début H", min_value=0, max_value=23, value=13, key="debut_h_ramasse")
    debut_m_r = col_debut_m_r.number_input("Début M", min_value=0, max_value=59, value=0, key="debut_m_ramasse")
    fin_h_r = col_fin_h_r.number_input("Fin H", min_value=0, max_value=23, value=17, key="fin_h_ramasse")
    fin_m_r = col_fin_m_r.number_input("Fin M", min_value=0, max_value=59, value=0, key="fin_m_ramasse")
    
    temps_service_ramasse_min = st.number_input("Temps de service estimé (minutes) :", min_value=1, value=10, key="temps_service_ramasse")

    if st.button("Ajouter cette Ramasse", key="add_ramasse_btn"):
        if nom_ramasse and adresse_ramasse:
            fenetre_horaire_minutes_r = (debut_h_r * 60 + debut_m_r, fin_h_r * 60 + fin_m_r)
            if fenetre_horaire_minutes_r[0] >= fenetre_horaire_minutes_r[1]:
                 st.warning("L'heure de début de la fenêtre horaire doit être avant l'heure de fin.")
            else:
                nouvelle_ramasse = PointInteret(
                    nom=nom_ramasse,
                    adresse=adresse_ramasse,
                    type_point="Ramasse",
                    contraintes={
                        "temps_service": timedelta(minutes=temps_service_ramasse_min),
                        "fenetre_horaire": fenetre_horaire_minutes_r,
                        "inclure_dans_aller": inclure_dans_aller_ramasse
                    }
                )
                st.session_state.points_data["ramasses"].append(nouvelle_ramasse)
                # Vider les champs pour la prochaine saisie
                st.session_state.nom_ramasse_input = ""
                st.session_state.adresse_ramasse_input = ""
                st.rerun()
        else:
            st.warning("Veuillez renseigner le nom et l'adresse de la ramasse.")

# --- Affichage des points ajoutés ---
st.header("Liste des Points de Passage Ajoutés")

col_livraisons, col_ramasses = st.columns(2)

with col_livraisons:
    st.subheader("Livraisons")
    if not st.session_state.points_data["livraisons"]:
        st.info("Aucune livraison ajoutée pour le moment.")
    else:
        for i, point in enumerate(st.session_state.points_data["livraisons"]):
            st.write(f"**{point.nom}** ({point.type_point})")
            st.caption(f"📍 {point.adresse}")
            if point.get_fenetre_horaire_str():
                st.caption(f"⏰ Fenêtre : {point.get_fenetre_horaire_str()}")
            st.caption(f"⏱️ Service : {point.temps_service.total_seconds() // 60} min")
            
            # Bouton pour supprimer le point
            if st.button("Supprimer", key=f"del_liv_{i}"):
                st.session_state.points_data["livraisons"].pop(i)
                st.rerun()
            st.markdown("---")

with col_ramasses:
    st.subheader("Ramasses")
    if not st.session_state.points_data["ramasses"]:
        st.info("Aucune ramasse ajoutée pour le moment.")
    else:
        for i, point in enumerate(st.session_state.points_data["ramasses"]):
            prefix = ">> " if point.inclure_dans_aller else ""
            st.write(f"**{prefix}{point.nom}** ({point.type_point})")
            st.caption(f"📍 {point.adresse}")
            if point.inclure_dans_aller:
                st.caption("✨ Traitée dans l'aller")
            if point.get_fenetre_horaire_str():
                st.caption(f"⏰ Fenêtre : {point.get_fenetre_horaire_str()}")
            st.caption(f"⏱️ Service : {point.temps_service.total_seconds() // 60} min")
            
            # Bouton pour supprimer le point
            if st.button("Supprimer", key=f"del_ram_{i}"):
                st.session_state.points_data["ramasses"].pop(i)
                st.rerun()
            st.markdown("---")

# --- Bouton pour lancer l'optimisation ---
if st.button("🚀 Calculer la meilleure tournée", key="calculate_btn"):
    if not depart_adresse_initiale:
        st.error("Veuillez renseigner l'adresse de départ.")
    elif not st.session_state.points_data["livraisons"] and not st.session_state.points_data["ramasses"]:
        st.warning("Veuillez ajouter au moins un point de passage (livraison ou ramasse).")
    else:
        # Appel de la fonction d'optimisation
        tournee_optimisee, duree_totale_estimee = optimiser_tournee(
            st.session_state.points_data["livraisons"],
            st.session_state.points_data["ramasses"],
            depart_adresse_initiale,
            heure_debut_tournee_obj
        )

        st.header("Planification Détaillée de la Tournée")
        
        if not tournee_optimisee:
            st.info("Aucune tournée calculée. Veuillez vérifier les points ajoutés.")
        else:
            total_temps_parcours = timedelta()
            total_attente = timedelta()
            
            st.write(f"**Adresse de départ :** {depart_adresse_initiale}")
            st.write(f"**Heure de début :** {heure_debut_tournee_obj.strftime('%H:%M')}")
            st.write(f"**Durée totale estimée de la tournée :** {formater_duree(duree_totale_estimee)}")
            st.markdown("---")

            for i, etape in enumerate(tournee_optimisee):
                point = etape["point"]
                
                prefix_type = ""
                if point.est_livraison():
                    prefix_type = "✅ **Livraison :**"
                elif point.est_ramasse():
                    prefix_type = "📦 **Ramasse :**"
                    if point.inclure_dans_aller:
                        prefix_type = "✨ **Ramasse (Aller) :**"
                
                st.write(f"{i+1}. {prefix_type} **{point.nom}**")
                st.caption(f"📍 {point.adresse}")
                st.caption(f"   Arrivée : {etape['heure_arrivee'].strftime('%H:%M:%S')} | Attente : {formater_duree(etape['attente'])} | Départ : {etape['heure_depart'].strftime('%H:%M:%S')}")
                
                if etape["duree_trajet_precedente"].total_seconds() > 0:
                    st.caption(f"   Trajet depuis point précédent : {formater_duree(etape['duree_trajet_precedente'])}")

                total_temps_parcours += etape["duree_trajet_precedente"]
                total_attente += etape["attente"]
                
                st.markdown("---")

            # Résumé des temps
            st.subheader("Récapitulatif des Temps")
            st.write(f"Temps total de trajet entre les points : {formater_duree(total_temps_parcours)}")
            st.write(f"Temps total d'attente aux fenêtres horaires : {formater_duree(total_attente)}")
            st.write(f"Temps total de service aux arrêts : {sum([p['point'].temps_service for p in tournee_optimisee], timedelta())}")
            st.write(f"Durée totale estimée de la tournée : {formater_duree(duree_totale_estimee)}")

# --- Instructions ---
st.sidebar.header("Instructions")
st.sidebar.markdown("""
1.  **Configurez votre départ :** Entrez l'adresse de départ et l'heure de début.
2.  **Ajoutez les points :** Utilisez les sections 'Ajouter une Livraison' et 'Ajouter une Ramasse'.
    *   Pour les livraisons, spécifiez la fenêtre horaire et le temps de service.
    *   Pour les ramasses, décidez si elle doit être traitée dans l'aller ('Inclure dans l'aller').
3.  **Vérifiez la liste :** Assurez-vous que tous les points sont corrects. Vous pouvez les supprimer.
4.  **Calculez la tournée :** Cliquez sur 'Calculer la meilleure tournée'.
5.  **Consultez le résultat :** L'itinéraire optimisé s'affichera avec les horaires détaillés.
""")
st.sidebar.markdown("---")
st.sidebar.info("Ce script utilise l'API Google Maps. Assurez-vous que votre clé API est valide et autorisée.")
