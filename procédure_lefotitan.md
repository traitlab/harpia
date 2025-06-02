# Ouvrir un  terminal

# Taper les commandes: 

```
cd /app/lefolab-dji-waypoints/
source /app/lefolab-dji-waypoints/.venv/bin/activate
```

# Créer un fichier de configuration pour la mission

```
cp /app/lefolab-dji-waypoints/config/settings.yaml /app/lefolab-dji-waypoints/config/settings@lefotitan_20240529_sblz1z2_p1.yaml
```

# Adapter les propriétés suivantes du fichier de configuration à votre mission : 

```
nano /app/lefolab-dji-waypoints/config/settings@lefotitan_20240529_sblz1z2_p1.yaml
```

- flight_height
- takeoff_point_elevation
- point_dsm_height_approach
- point_dsm_height_buffer
- base_name
- points_csv_file_path

# Sauvegarder le fichier de configuration

# Exécuter le script en utilisant le fichier de configuration: 

```
python /app/lefolab-dji-waypoints/src/main.py --config /app/lefolab-dji-waypoints/config/settings@lefotitan_20240529_sblz1z2_p1.yaml
```

# Les résultats sont dans `/data/xprize/<missionid­>`

Il y a un fichier .kmz (<missionid­>_<datetime>.kmz). C’est ce qui doit être transféré sur la manette. 
Les fichiers KML et WPML qui sont dans le fichier KML sont dans `/data/xprize/<missionid­>/wpmz`

# Désactiver l'environnement virtuel Python une fois complété

`deactivate`


