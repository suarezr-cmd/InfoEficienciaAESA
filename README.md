# Eficiencia de Planta

Aplicación web para consultar eficiencia y producción de planta a partir de archivos SAP, HPHI y DENCRE.

## Requisitos

- Python 3.10 o superior
- Dependencias de `requirements.txt`
- Los archivos de datos operativos requeridos, que no se versionan en este repositorio

## Instalación y ejecución

1. Crear y activar un entorno virtual.
2. Instalar dependencias:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Colocar los archivos Excel de trabajo en la ubicación configurada localmente.
4. Iniciar la aplicación:

   ```powershell
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

La aplicación crea y utiliza `eficiencia_historia.db` en el directorio de trabajo. La base de datos y los archivos operativos están excluidos de Git.

## Datos excluidos

El repositorio no debe contener bases de datos de producción, hojas de cálculo operativas, respaldos, entornos virtuales ni secretos. Al desplegar o desarrollar, esos datos deben mantenerse localmente y compartirse por los canales internos autorizados.
