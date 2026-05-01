"""
Script d'import des données employés depuis un fichier Excel.
"""
import os
from datetime import datetime
from pathlib import Path

import openpyxl
from werkzeug.security import generate_password_hash

from app import db
from app.models import User, Role, Employee, Department, Position


def import_employees_from_excel(excel_path: str) -> dict:
    """
    Importe les employés depuis un fichier Excel.
    
    Structure réelle du fichier (colonne 0 = Matricule) :
    - Matricule, Civilité, Nom, Nom de naissance, Prénom, Adresse, CP, Ville
    - Date de naissance, Ville et Pays de naissance, Nationalité, N° de SS
    - TYPE DE CONTRAT, Embauche, Période d'Essai, Fin de contrat, Durée contrat
    - Poste, Niveau, Indice, Nb h/semaine, Nb h/mois
    - Salaire horaire, Salaire mensuel Brut, Navigo, Taux PAS
    
    :param excel_path: Chemin du fichier Excel
    :return: Dictionnaire avec nombre d'employés importés et erreurs
    """
    results = {
        "imported": 0,
        "errors": [],
        "skipped": 0
    }
    
    if not os.path.exists(excel_path):
        results["errors"].append(f"Fichier non trouvé : {excel_path}")
        return results
    
    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        
        # Récupérer ou créer le rôle 'staff'
        staff_role = Role.query.filter_by(name='staff').first()
        if not staff_role:
            staff_role = Role(name='staff')
            db.session.add(staff_role)
            db.session.commit()
        
        # Récupérer/créer le département par défaut
        default_dept = Department.query.filter_by(name='Administration').first()
        if not default_dept:
            default_dept = Department(name='Administration')
            db.session.add(default_dept)
            db.session.commit()
        
        # Parcourir les lignes (première ligne = en-têtes)
        rows_data = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows_data.append(row)
        
        for row_idx, row in enumerate(rows_data, start=2):
            try:
                # Extraction des colonnes (Matricule en col 0)
                matricule_raw = row[0]
                civility = row[1]
                last_name = row[2]
                birth_name = row[3]
                first_name = row[4]
                address = row[5]
                zip_code = str(row[6]).strip() if row[6] else None
                city = row[7]
                birth_date_val = row[8]
                birth_place = row[9]
                nationality = row[10]
                social_security = str(row[11]).strip() if row[11] else None
                contract_type = row[12]
                hire_date_val = row[13]
                trial_period_val = row[14]
                contract_end_val = row[15]
                contract_duration = row[16]
                position_title = row[17]
                level = row[18]
                index_grade = str(row[19]).strip() if row[19] else None
                hours_per_week = row[20]
                hours_per_month = row[21]
                hourly_rate = row[22]
                monthly_salary = row[23]
                navigo_str = row[24]
                pas_rate = row[25] if len(row) > 25 else None
                
                # Convertir matricule en chaîne et padder à 5 chiffres
                matricule = str(int(matricule_raw)).zfill(5) if matricule_raw is not None else None
                
                # Validation minimale
                if not first_name or not last_name:
                    results["errors"].append(f"Ligne {row_idx}: Prénom ou Nom manquant")
                    results["skipped"] += 1
                    continue
                
                # Valider le matricule
                if not matricule:
                    results["errors"].append(f"Ligne {row_idx} ({first_name} {last_name}): Matricule manquant")
                    results["skipped"] += 1
                    continue
                
                # Vérifier l'unicité du matricule
                existing_by_matricule = Employee.query.filter_by(employee_id=matricule).first()
                if existing_by_matricule:
                    results["errors"].append(f"Ligne {row_idx}: Matricule {matricule} déjà utilisé")
                    results["skipped"] += 1
                    continue
                
                # Vérifier si l'employé existe déjà (par email)
                email = f"{first_name.lower()}.{last_name.lower()}@edumanager.local".replace(" ", "")
                if User.query.filter_by(email=email).first():
                    results["skipped"] += 1
                    continue
                
                # Traiter les dates
                hire_date = _parse_excel_date(hire_date_val)
                birth_date = _parse_excel_date(birth_date_val)
                trial_period_end = _parse_excel_date(trial_period_val)
                contract_end_date = _parse_excel_date(contract_end_val)
                
                # Créer/récupérer la position
                position = None
                if position_title:
                    position = Position.query.filter_by(title=position_title).first()
                    if not position:
                        position = Position(title=position_title)
                        db.session.add(position)
                        db.session.flush()
                
                # Créer l'utilisateur
                user = User(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password_hash=generate_password_hash("temp_password_123"),
                    role=staff_role
                )
                db.session.add(user)
                db.session.flush()
                
                # Utiliser le matricule du fichier Excel
                employee_id = matricule
                
                # Traiter navigo (convert "Oui"/"Non" ou true/false)
                navigo_pass = False
                if navigo_str:
                    navigo_str_lower = str(navigo_str).lower()
                    navigo_pass = navigo_str_lower in ("oui", "true", "yes", "1", 1, True)
                
                # Créer l'employé
                employee = Employee(
                    user=user,
                    hire_date=hire_date,
                    employee_id=employee_id,
                    social_security_number=social_security,
                    contract_end_date=contract_end_date,
                    position=position,
                    department=default_dept,
                    birth_name=birth_name,
                    birth_date=birth_date,
                    birth_place=birth_place,
                    nationality=nationality,
                    civility=civility,
                    address=address,
                    zip_code=zip_code,
                    city=city,
                    contract_type=contract_type,
                    trial_period_end=trial_period_end,
                    contract_duration=_to_float(contract_duration),
                    level=level,
                    index_grade=index_grade,
                    hours_per_week=_to_float(hours_per_week),
                    hours_per_month=_to_float(hours_per_month),
                    hourly_rate=_to_float(hourly_rate),
                    monthly_salary=_to_float(monthly_salary),
                    navigo_pass=navigo_pass,
                    pas_rate=_to_float(pas_rate)
                )
                db.session.add(employee)
                db.session.commit()
                
                results["imported"] += 1
                
            except Exception as e:
                db.session.rollback()
                results["errors"].append(f"Ligne {row_idx}: {str(e)}")
        
        return results
        
    except Exception as e:
        results["errors"].append(f"Erreur lors de la lecture du fichier : {str(e)}")
        return results


def _parse_excel_date(val):
    """Convertit une valeur Excel en date."""
    if not val:
        return None
    if isinstance(val, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    # openpyxl retourne déjà des objets datetime pour les dates
    if hasattr(val, 'date'):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    return None


def _to_float(val):
    """Convertit une valeur en float."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
