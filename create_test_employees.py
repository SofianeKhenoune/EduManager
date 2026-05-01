#!/usr/bin/env python3
"""Crée un fichier Excel de test avec quelques employés."""

import openpyxl
from datetime import datetime, date

# Créer un workbook
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Employés"

# En-têtes
headers = [
    "Civilité", "Nom", "Nom de naissance", "Prénom", "Adresse", "CP", "Ville",
    "Date de naissance", "Ville et Pays de naissance", "Nationalité", "N° de SS",
    "TYPE DE CONTRAT", "Embauche", "Période d'Essai", "Fin de contrat", "Durée contrat",
    "Poste", "Niveau", "Indice", "Nb h/semaine", "Nb h/mois",
    "Salaire horaire", "Salaire mensuel Brut", "Navigo", "Taux PAS"
]

ws.append(headers)

# Données de test
test_employees = [
    [
        "M.", "Dupont", "Martin", "Jean",
        "123 rue de la Paix", "75001", "Paris",
        date(1985, 3, 15), "Paris, France", "Français", "123456789012345",
        "CDI", date(2020, 9, 1), date(2020, 11, 30), None, None,
        "Directeur Pédagogique", "Niveau 1", "Indice 100", 35.0, 150.0,
        25.50, 3825.00, "Oui", 10.5
    ],
    [
        "Mme", "Martin", "Nicole", "Sophie",
        "456 avenue des Champs", "75008", "Paris",
        date(1990, 7, 22), "Lyon, France", "Française", "234567890123456",
        "CDI", date(2021, 1, 15), date(2021, 4, 14), None, None,
        "Professeur Principal", "Niveau 2", "Indice 80", 35.0, 150.0,
        22.00, 3300.00, "Oui", 8.0
    ],
    [
        "M.", "Bernard", "Claude", "Michel",
        "789 rue de la Fontaine", "92200", "Neuilly", 
        date(1978, 11, 3), "Marseille, France", "Français", "345678901234567",
        "CDI", date(2019, 6, 1), date(2019, 8, 31), None, None,
        "Coordinateur Administratif", "Niveau 3", "Indice 60", 35.0, 150.0,
        18.75, 2812.50, "Non", 5.0
    ]
]

for employee in test_employees:
    ws.append(employee)

# Sauvegarder
import os
file_path = os.path.join(os.path.dirname(__file__), "LISTE_SALARIES_25-26.xlsx")
wb.save(file_path)
print(f"✓ Fichier de test créé : {file_path}")
