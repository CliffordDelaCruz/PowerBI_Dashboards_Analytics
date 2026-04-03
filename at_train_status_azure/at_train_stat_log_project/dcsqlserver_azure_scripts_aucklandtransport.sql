
# Create a database - auckland_transport_db
CREATE DATABASE auckland_transport_db;

# check if the user already exists before creating
DROP USER IF EXISTS 'atpythonuser01'@'%';

# Create user atpythonuser01
CREATE USER 'atpythonuser01'@'%' IDENTIFIED BY 'Passw0rd01!';
GRANT ALL PRIVILEGES ON auckland_transport_db.* TO 'atpythonuser01'@'%';
# Apply the role immediately
FLUSH PRIVILEGES;

#display role for atpythonuser01
SHOW GRANTS FOR 'atpythonuser01'@'%';

SELECT CURRENT_USER();

select * from attrainstoplog;

# Set the database as default and proceed to create table attrainstoplog
USE auckland_transport_db;

CREATE TABLE attrainstoplog (
    PKEY INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    DateTimeExtracted DATETIME NOT NULL,
    TrainLine VARCHAR(50) NOT NULL,
    Status VARCHAR(30) NOT NULL,
    WhereTaken VARCHAR(50) NOT NULL,
    Route_ID VARCHAR(20) NOT NULL,
    Trip_ID VARCHAR(50)
);