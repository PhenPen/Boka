# Boka — clinic booking API

A JSON API for booking clinic appointment slots, plus a single-page front end that
uses it. Built to the contract published at
<https://koyaacademy.com/assessment-api>.

FastAPI + Postgres. Every request needs an `X-API-Key` header.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/reset` | Replace all slots, delete all bookings |
| `GET` | `/slots` | List slots, earliest first, with `available` |
| `POST` | `/bookings` | Book a slot |
| `GET` | `/bookings` | A person's bookings, cursor paginated |
| `GET` | `/bookings/{id}` | One booking |
| `DELETE` | `/bookings/{id}` | Cancel a booking |

## Local development

TODO — filled in as the build lands.
