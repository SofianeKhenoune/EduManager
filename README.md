# EduManager

Application Python de gestion des élèves, enseignants, professeurs et salariés sur deux sites, avec un système robuste de planning, d'inscriptions et de gestion globale.

---

## Analyse du Projet

### Idée

Gérer efficacement les ressources humaines (élèves, enseignants, professeurs, salariés) sur deux sites avec un système de planning et d'inscriptions.

### Problème à résoudre

- Gestion des utilisateurs divers (élèves, enseignants, professeurs, salariés)
- Planification des horaires
- Inscriptions aux cours et événements
- Gestion globale des ressources
- Sécurité et accès contrôlés

### Cible

Organisation scolaire efficace et facile à utiliser.

### Proposition de valeur

Système complet pour la gestion administrative d'une organisation éducative.

---

## MVP conseillé

- Gestion des utilisateurs
- Système de planning simple
- Inscriptions aux cours

---

## Fonctionnalités

### Prioritaires

- Ajout et gestion des utilisateurs (élèves, enseignants, professeurs, salariés)
- Création et modification de plans horaires
- Inscription des élèves aux cours
- Génération de rapports

### Futures

- Facturation et paiement en ligne
- Système de notes et évaluations
- Communication interne

---

## Contraintes et Risques

| Contrainte | Description |
|---|---|
| Temps de développement | Délais limités — prioriser le MVP |
| Sécurité des données | Protection des informations personnelles obligatoire |
| Contrôle d'accès | Droits différenciés selon le rôle de l'utilisateur |

---

## Stack Technique

| Couche | Technologie |
|---|---|
| Backend | Python / Flask |
| ORM | SQLAlchemy |
| Authentification | Flask-Login |
| Frontend | React ou Vue.js |
| Planning | FullCalendar.js |
| Base de données | SQLite (dev) / PostgreSQL (prod) |

---

## Plan d'action

1. Installer Flask et les dépendances
2. Créer les modèles SQLAlchemy (utilisateurs, cours, horaires)
3. Implémenter l'authentification avec Flask-Login
4. Développer la page de login / administration
5. Créer les vues CRUD pour gérer les utilisateurs
6. Implémenter le planning avec FullCalendar.js
7. Ajouter la fonctionnalité d'inscription des élèves

---

## Structure de la base de données

Voir [schema.sql](schema.sql) et [schema.md](schema.md) pour le détail des tables.

---

## Installation

```bash
# Cloner le dépôt
git clone <url-du-repo>
cd EduManager

# Créer un environnement virtuel
python -m venv venv
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install flask flask-login flask-sqlalchemy

# Lancer l'application
flask run
```

---

## Licence

MIT
