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

## Relations

- `users.role_id` fait référence à `roles.id`
