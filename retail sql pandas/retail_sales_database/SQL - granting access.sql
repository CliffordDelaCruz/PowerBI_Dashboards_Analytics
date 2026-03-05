#Create user - in this example, pythonuser1
CREATE USER 'pythonuser1'@'localhost' IDENTIFIED BY 'P@ssw0rd01!';

#If need to alter, use this update script
ALTER USER 'pythonuser1'@'localhost'
IDENTIFIED WITH mysql_native_password BY 'Passw0rd01!';

#Grant 'retail_sales_database' to pythonuser1
GRANT SELECT ON `retail_sales_database`.* TO 'pythonuser1'@'localhost';

#Apply immediately
FLUSH PRIVILEGES;

#display role for pythonuser1
SHOW GRANTS FOR 'pythonuser1'@'localhost';