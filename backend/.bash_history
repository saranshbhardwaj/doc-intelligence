alembic revision --autogenerate -m "add snapshot columns to extractions"
clear
alembic revision --autogenerate -m "jsonb cols"
clear
alembic current
alembic upgrade head
clear
alembic current
alembic upgrade head
clear
alembic upgrade head
clear
alembic upgrade head
clear
alembic upgrade head
clear
alembic upgrade head
clear
alembic upgrade head
exit
