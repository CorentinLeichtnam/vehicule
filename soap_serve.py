from flask import Flask, request, jsonify, render_template
from geopy.geocoders import Nominatim
from math import radians, sin, cos, sqrt, atan2

# Initialisation de l'application Flask
app = Flask(__name__)

# Fonction de calcul de distance avec la formule de Haversine
def calculer_distance_haversine(lat1, lon1, lat2, lon2):
    # Rayon de la Terre en kilomètres
    R = 6371.0
    
    # Convertir les degrés en radians
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)
    
    # Différences des coordonnées
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    # Calcul de la distance
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    # Distance en kilomètres
    distance = R * c
    return distance

# Route Flask pour calculer la distance
@app.route('/distance', methods=['POST'])
def distance():
    # Récupérer les données JSON envoyées dans la requête
    data = request.get_json()
    ville1 = data.get('ville1')
    ville2 = data.get('ville2')

    # Initialiser le géolocalisateur (Nominatim de geopy)
    geolocator = Nominatim(user_agent="myApp")
    
    # Récupérer les coordonnées des villes
    location1 = geolocator.geocode(ville1)
    location2 = geolocator.geocode(ville2)

    # Vérifier si les villes ont été trouvées
    if location1 and location2:
        # Calculer la distance avec la fonction Haversine
        distance_km = calculer_distance_haversine(location1.latitude, location1.longitude, location2.latitude, location2.longitude)
        return jsonify({'distance': f'{distance_km:.2f} km'})
    else:
        return jsonify({'error': 'Une des villes est invalide ou introuvable'}), 400

# Route pour la page d'accueil
@app.route('/')
def home():
    return render_template('indextest.html')  # Charge le fichier HTML à la racine

# Route pour le favicon.ico
@app.route('/favicon.ico')
def favicon():
    return '', 204  # Réponse vide, juste pour éviter l'erreur

# Lancer l'application Flask sur le port 5002
if __name__ == '__main__':
    app.run(debug=True, port=5002)
