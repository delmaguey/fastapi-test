from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello Daniel from FastAPI!"}


@app.get("/age/{year}")
def calculate_age(year:int):

    age = 2026 - year

    return {
        "birthYear": year,
        "age": age
    }