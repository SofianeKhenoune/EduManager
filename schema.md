# Schéma de la base de données

## Table `roles`

| Colonne | Type    | Contraintes          |
|---------|---------|----------------------|
| id      | INTEGER | PRIMARY KEY, AUTOINCREMENT |
| name    | TEXT    | NOT NULL, UNIQUE     |

## Table `users`

| Colonne       | Type    | Contraintes                        |
|---------------|---------|------------------------------------|
| id            | INTEGER | PRIMARY KEY, AUTOINCREMENT         |
| first_name    | TEXT    | NOT NULL                           |
| last_name     | TEXT    | NOT NULL                           |
| email         | TEXT    | NOT NULL, UNIQUE                   |
| password_hash | TEXT    | NOT NULL                           |
| role_id       | INTEGER | FOREIGN KEY → `roles(id)`          |
| phone_number  | TEXT    |                                    |

## Table `teachers`

| Colonne | Type    | Contraintes                                 |
|---------|---------|---------------------------------------------|
| id      | INTEGER | PRIMARY KEY, AUTOINCREMENT                  |
| user_id | INTEGER | NOT NULL, UNIQUE, FOREIGN KEY → `users(id)` |
| subject | TEXT    |                                             |

## Table `sites`

| Colonne | Type    | Contraintes                |
|---------|---------|----------------------------|
| id      | INTEGER | PRIMARY KEY, AUTOINCREMENT |
| name    | TEXT    | NOT NULL, UNIQUE           |
| address | TEXT    |                            |

## Table `courses`

| Colonne     | Type    | Contraintes                                                                        |
|-------------|---------|------------------------------------------------------------------------------------|
| id          | INTEGER | PRIMARY KEY, AUTOINCREMENT                                                         |
| title       | TEXT    | NOT NULL                                                                           |
| description | TEXT    |                                                                                    |
| teacher_id  | INTEGER | NOT NULL, FOREIGN KEY → `teachers(id)`                                                 |
| site_id     | INTEGER | FOREIGN KEY → `sites(id)`                                                          |
| level       | TEXT    | Niveau du cours - CHECK IN (`PREPA`, `NIV1`, `NIV2`, `NIV3`, `NIV4`, `NIV5`, `NIV6`, `NIV7`) |
| day         | TEXT    | CHECK IN (`lundi`, `mardi`, `mercredi`, `jeudi`, `vendredi`, `samedi`, `dimanche`) |
| time_slot   | TEXT    | CHECK IN (`matin`, `après-midi`)                                                   |
| start_hour  | INTEGER | CHECK BETWEEN 0 ET 23                                                              |
| end_hour    | INTEGER | CHECK BETWEEN 0 ET 23, et `end_hour > start_hour`                                 |

## Table `students`

| Colonne           | Type    | Contraintes                     |
|-------------------|---------|---------------------------------|
| id                | INTEGER | PRIMARY KEY, AUTOINCREMENT      |
| user_id           | INTEGER | NOT NULL, UNIQUE, FOREIGN KEY → `users(id)` |
| site_id           | INTEGER | FOREIGN KEY → `sites(id)`       |
| father_first_name | TEXT    |                                 |
| father_last_name  | TEXT    |                                 |
| father_email      | TEXT    |                                 |
| father_phone      | TEXT    |                                 |
| mother_first_name | TEXT    |                                 |
| mother_last_name  | TEXT    |                                 |
| mother_email      | TEXT    |                                 |
| mother_phone      | TEXT    |                                 |
| address_number    | INTEGER | CONSTRAINT `check_address_number` CHECK >= 0 |
| street            | TEXT    | NOT NULL                        |
| city              | TEXT    | NOT NULL                        |
| zip_code          | TEXT    | NOT NULL                        |
| birth_date        | DATE    | NOT NULL                        |
| lives_alone       | BOOLEAN | DEFAULT FALSE                   |

## Table `enrollments`

| Colonne         | Type    | Contraintes                               |
|-----------------|---------|-------------------------------------------|
| id              | INTEGER | PRIMARY KEY, AUTOINCREMENT                |
| student_id      | INTEGER | NOT NULL, FOREIGN KEY → `students(id)`    |
| course_id       | INTEGER | NOT NULL, FOREIGN KEY → `courses(id)`     |
| enrollment_date | DATE    | NOT NULL, DEFAULT `CURRENT_DATE`                          |
| status          | TEXT    | CHECK IN (`active`, `annulee`, `en_attente`) |

> Contrainte : `UNIQUE (student_id, course_id)` — un élève ne peut s'inscrire qu'une fois au même cours.

## Table `payments`

| Colonne      | Type            | Contraintes                        |
|--------------|-----------------|------------------------------------|
| id           | INTEGER         | PRIMARY KEY, AUTOINCREMENT         |
| student_id   | INTEGER         | FOREIGN KEY → `students(id)`       |
| total_amount | DECIMAL(10, 2)  |                                    |
| payment_date | DATE            |                                    |
| method       | TEXT            | CHECK IN (`CB`, `ESP`, `CHQ`)      |

## Table `payments_n`

| Colonne            | Type            | Contraintes                                 |
|--------------------|-----------------|---------------------------------------------|
| id                 | INTEGER         | PRIMARY KEY, AUTOINCREMENT                  |
| payment_id         | INTEGER         | FOREIGN KEY → `payments(id)`                |
| installment_number | INTEGER         | CHECK BETWEEN 1 AND 6                       |
| amount             | DECIMAL(10, 2)  |                                             |
| payment_date       | DATE            |                                             |
| method             | TEXT            | CHECK IN (`CB`, `ESP`, `CHQ`)               |

## Table `employees`

| Colonne                | Type    | Contraintes                           |
|------------------------|---------|---------------------------------------|
| id                     | INTEGER | PRIMARY KEY, AUTOINCREMENT            |
| user_id                | INTEGER | NOT NULL, UNIQUE, FOREIGN KEY → `users(id)` |
| hire_date              | DATE    | NOT NULL                              |
| employee_id            | TEXT    | NOT NULL, UNIQUE                      |
| social_security_number | TEXT    | UNIQUE                                |
| contract_end_date      | DATE    | Renseigné pour les CDD                |
| position_id            | INTEGER | FOREIGN KEY → `positions(id)`         |
| department_id          | INTEGER | FOREIGN KEY → `departments(id)`       |

## Table `departments`

| Colonne    | Type    | Contraintes                           |
|------------|---------|---------------------------------------|
| id         | INTEGER | PRIMARY KEY, AUTOINCREMENT            |
| name       | TEXT    | NOT NULL                              |
| manager_id | INTEGER | FOREIGN KEY → `employees(id)`         |

## Table `positions`

| Colonne     | Type    | Contraintes                |
|-------------|---------|----------------------------|
| id          | INTEGER | PRIMARY KEY, AUTOINCREMENT |
| title       | TEXT    | NOT NULL                   |
| description | TEXT    |                            |

## Table `salary_details`

| Colonne       | Type    | Contraintes                    |
|---------------|---------|--------------------------------|
| id            | INTEGER | PRIMARY KEY, AUTOINCREMENT     |
| employee_id   | INTEGER | FOREIGN KEY → `employees(id)`  |
| contract_type | TEXT    | NOT NULL                       |
| hourly_rate   | REAL    |                                |
| annual_salary | REAL    |                                |
| benefits      | TEXT    |                                |

## Table `performance_reviews`

| Colonne     | Type    | Contraintes                    |
|-------------|---------|--------------------------------|
| id          | INTEGER | PRIMARY KEY, AUTOINCREMENT     |
| employee_id | INTEGER | FOREIGN KEY → `employees(id)`  |
| review_date | DATE    | NOT NULL                       |
| rating      | INTEGER | NOT NULL                       |
| comments    | TEXT    |                                |

## Table `employee_leave_requests`

| Colonne     | Type    | Contraintes                    |
|-------------|---------|--------------------------------|
| id          | INTEGER | PRIMARY KEY, AUTOINCREMENT     |
| employee_id | INTEGER | FOREIGN KEY → `employees(id)`  |
| start_date  | DATE    | NOT NULL                       |
| end_date    | DATE    | NOT NULL                       |
| leave_type  | TEXT    | NOT NULL                       |
| status      | TEXT    | NOT NULL, DEFAULT `pending`    |
| comments    | TEXT    |                                |

## Contraintes complémentaires

- `payments_n` impose l'unicité de `(payment_id, installment_number)` via `unique_installment_number`.
- La validation du format de `phone_number` n'est pas définie dans ce schéma SQL. En SQLite, cela se gère plutôt via `TRIGGER` ou validation applicative.

## Donnees initiales

- Roles recommandes: `admin`, `teacher`, `student`, `staff`, `manager`, `volunteer` (insérés via `INSERT OR IGNORE`).
- `staff` couvre le personnel administratif non-enseignant (secrétaires, accueil, assistants).
- `manager` est destiné à la direction.

## Relations

- `users.role_id` fait référence à `roles.id`
- `teachers.user_id` fait référence à `users.id`
- `courses.teacher_id` fait référence à `teachers.id`
- `courses.site_id` fait référence à `sites.id`
- `students.user_id` fait référence à `users.id`
- `students.site_id` fait référence à `sites.id`
- `enrollments.student_id` fait référence à `students.id`
- `enrollments.course_id` fait référence à `courses.id`
- `payments.student_id` fait référence à `students.id`
- `payments_n.payment_id` fait référence à `payments.id`
- `employees.user_id` fait référence à `users.id`
- `employees.position_id` fait référence à `positions.id`
- `employees.department_id` fait référence à `departments.id`
- `departments.manager_id` fait référence à `employees.id`
- `salary_details.employee_id` fait référence à `employees.id`
- `performance_reviews.employee_id` fait référence à `employees.id`
- `employee_leave_requests.employee_id` fait référence à `employees.id`
