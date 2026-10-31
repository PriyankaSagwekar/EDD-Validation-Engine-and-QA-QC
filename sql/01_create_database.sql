/* 01 - Create the EnvDataQC database.
   Run with sqlcmd: sqlcmd -S .\SQLEXPRESS -E -b -I -v DbName=EnvDataQC -i 01_create_database.sql
   The Python "init-db --reset" command drops the database first. */
IF DB_ID(N'$(DbName)') IS NULL
BEGIN
    CREATE DATABASE [$(DbName)];
END
GO
ALTER DATABASE [$(DbName)] SET RECOVERY SIMPLE;
GO
