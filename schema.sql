-- Création de la table 'roles'
CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Création de la table 'users'
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INTEGER,
    phone_number TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

-- Création de la table 'teachers'
CREATE TABLE teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    subject TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Création de la table 'sites'
CREATE TABLE sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT
);

-- Création de la table 'courses'
CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    teacher_id INTEGER NOT NULL,
    site_id INTEGER,
    level TEXT,
    day TEXT,
    time_slot TEXT,
    start_hour INTEGER,
    end_hour INTEGER,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id),
    FOREIGN KEY (site_id) REFERENCES sites(id),
    CONSTRAINT check_time_slot CHECK (time_slot IN ('matin', 'après-midi')),
    CONSTRAINT check_day CHECK (day IN ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')),
    CONSTRAINT check_level CHECK (level IN ('PREPA', 'NIV1', 'NIV2', 'NIV3', 'NIV4', 'NIV5', 'NIV6', 'NIV7')),
    CONSTRAINT check_start_hour CHECK (start_hour BETWEEN 0 AND 23),
    CONSTRAINT check_end_hour CHECK (end_hour BETWEEN 0 AND 23),
    CONSTRAINT check_hours_order CHECK (end_hour > start_hour)
);

-- Création de la table 'students'
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    site_id INTEGER,
    father_first_name TEXT,
    father_last_name TEXT,
    father_email TEXT,
    father_phone TEXT,
    mother_first_name TEXT,
    mother_last_name TEXT,
    mother_email TEXT,
    mother_phone TEXT,
    address_number INTEGER,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    birth_date DATE NOT NULL,
    lives_alone BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (site_id) REFERENCES sites(id),
    CONSTRAINT check_address_number CHECK (address_number >= 0)
);

-- Création de la table 'enrollments'
CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    enrollment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT CHECK (status IN ('active', 'annulee', 'en_attente')),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    CONSTRAINT unique_enrollment UNIQUE (student_id, course_id)
);

-- Création de la table 'payments'
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    total_amount DECIMAL(10, 2),
    payment_date DATE,
    method TEXT CHECK (method IN ('CB', 'ESP', 'CHQ')),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

-- Création de la table 'payments_n'
CREATE TABLE payments_n (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER,
    installment_number INTEGER CHECK(installment_number BETWEEN 1 AND 6),
    amount DECIMAL(10, 2),
    payment_date DATE,
    method TEXT CHECK (method IN ('CB', 'ESP', 'CHQ')),
    FOREIGN KEY (payment_id) REFERENCES payments(id),
    CONSTRAINT unique_installment_number UNIQUE (payment_id, installment_number)
);

-- Création de la table 'employees'
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    hire_date DATE NOT NULL,
    employee_id TEXT UNIQUE NOT NULL,
    social_security_number TEXT UNIQUE,
    contract_end_date DATE,
    position_id INTEGER,
    department_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (position_id) REFERENCES positions(id),
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

-- Création de la table 'departments'
CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    manager_id INTEGER,
    FOREIGN KEY (manager_id) REFERENCES employees(id)
);

-- Création de la table 'positions'
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT
);

-- Création de la table 'salary_details'
CREATE TABLE salary_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    contract_type TEXT NOT NULL,
    hourly_rate REAL,
    annual_salary REAL,
    benefits TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Création de la table 'performance_reviews'
CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    review_date DATE NOT NULL,
    rating INTEGER NOT NULL,
    comments TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Création de la table 'employee_leave_requests'
CREATE TABLE employee_leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    leave_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    comments TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Donnees initiales recommandées pour les roles
INSERT OR IGNORE INTO roles (name) VALUES ('admin');
INSERT OR IGNORE INTO roles (name) VALUES ('teacher');
INSERT OR IGNORE INTO roles (name) VALUES ('student');
INSERT OR IGNORE INTO roles (name) VALUES ('staff');
INSERT OR IGNORE INTO roles (name) VALUES ('manager');
INSERT OR IGNORE INTO roles (name) VALUES ('volunteer');
