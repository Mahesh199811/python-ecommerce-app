# Stride

A local multi-brand shoe store. Every service is Python and FastAPI.

| Service | Port | Responsibility |
| --- | --- | --- |
| User | 5001 | Create and manage shoppers |
| Product | 5002 | Shoe catalog, brands, sizes, and stock |
| Order | 5003 | Create, list, and cancel orders |
| Storefront | 5004 | Shop UI at http://127.0.0.1:5004 |

The catalog includes Nike, Adidas, Puma, New Balance, Converse, ASICS, Vans, On, Hoka, and Reebok. Placing an order checks the customer, reserves that size, and stores the brand, size, and color on the order.

Interactive API docs:

- http://127.0.0.1:5001/docs
- http://127.0.0.1:5002/docs
- http://127.0.0.1:5003/docs

## Run locally

```bash
./scripts/run_local.sh
```

Stop everything with:

```bash
./scripts/stop_local.sh
```

Each service stores its own SQLite file under `data/`. Logs are written to `logs/`.

## Example

```bash
curl http://127.0.0.1:5002/products?brand=Nike

curl -X POST http://127.0.0.1:5003/orders \
  -H 'Content-Type: application/json' \
  -d '{"user_id": 1, "items": [{"product_id": 1, "quantity": 1}]}'
```
