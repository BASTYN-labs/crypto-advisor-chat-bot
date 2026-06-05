# CryptoAdvisor

AI-powered cryptocurrency investment advisor built with LangGraph, FastAPI, and RAG.

## Features

- **Live market data** — real-time prices via CoinGecko
- **Portfolio management** — track holdings, cash positions, and P&L
- **Trade workflow** — propose trades with human-in-the-loop approval
- **Deep research** — multi-hop agentic research across market sources
- **Document analysis** — upload whitepapers and investment memos for AI review
- **Risk assessment** — portfolio risk scoring with actionable recommendations
- **Gas fees** — Ethereum network fee estimates

## Architecture

```
User → FastAPI
         └── LangGraph StateGraph
               ├── rag_node        — TF-IDF retrieval over advisor personas
               ├── memory_node     — session context retrieval
               ├── advisor_node    — GPT-4o with tool calling
               ├── tools_node      — market data, portfolio, research
               └── output_node     — response handler
```

Multi-agent pipeline:
```
ResearchAgent → ExecutionAgent
     └── deep_research_loop (iterative tool-augmented research)
```

## Quick Start

```bash
cp .env.example .env          # add your OpenAI key
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://localhost:8000` for the chat interface or `http://localhost:8000/docs` for the full API explorer.

## Docker

```bash
docker build -t crypto-advisor .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-your-key crypto-advisor
```

---

## Scenarios

### 1. Live price lookup

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the current price of Solana?",
    "user_id": "user_001"
  }'
```

```json
{
  "reply": "SOL is currently trading at $142.37, up 3.2% in the last 24 hours. Market cap stands at $65.8B. Given your current position of 80 SOL (entry at $95.00), you are sitting on a 49.9% gain.",
  "debug_info": { "model_config": { ... }, "system_override_used": false }
}
```

---

### 2. Portfolio view

```bash
curl http://localhost:8000/portfolio/user_001
```

```json
{
  "user_id": "user_001",
  "holdings": {
    "BTC": { "amount": 0.45, "avg_price": 42000.0 },
    "ETH": { "amount": 3.2,  "avg_price": 2800.0  },
    "SOL": { "amount": 80.0, "avg_price": 95.0    },
    "USD": { "amount": 16420.0, "avg_price": 1.0  }
  }
}
```

Or via chat:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show my portfolio and suggest a rebalance.",
    "user_id": "user_001"
  }'
```

---

### 3. Trade proposal + approval

```bash
# Step 1 — propose
curl -X POST http://localhost:8000/trade/propose \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "coin": "ethereum",
    "direction": "buy",
    "amount_usd": 5000
  }'
```

```json
{
  "trade_id": "a3f9c812",
  "proposal": {
    "action": "BUY 1.3510 ETHEREUM",
    "price_locked": "$3,701.00",
    "total_usd": "$5,000.00"
  },
  "approve_endpoint": "POST /trade/approve/a3f9c812",
  "expires_in_seconds": 600
}
```

```bash
# Step 2 — approve
curl -X POST http://localhost:8000/trade/approve/a3f9c812
```

```json
{
  "status": "executed",
  "trade": {
    "direction": "buy",
    "coin": "ETHEREUM",
    "coins_traded": 1.351,
    "price": 3701.0,
    "total_usd": 5000.0
  },
  "updated_portfolio": { ... }
}
```

---

### 4. Whitepaper / document analysis

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze this document: XYZ Protocol — Delegated Proof of Stake, 21 validators, 1B token supply, 40% team allocation (4yr vest), cross-chain DEX with MEV protection. Unaudited contracts, anonymous team.",
    "user_id": "user_001"
  }'
```

```json
{
  "reply": "XYZ Protocol Assessment:\n\n**Thesis:** Cross-chain DEX targeting MEV-sensitive traders...\n**Risk factors:**\n- Unaudited smart contracts — critical risk\n- Anonymous founding team — no accountability\n- 40% team allocation creates significant dump risk at vesting cliff\n**Recommendation:** Speculative / avoid until audit complete. Confidence: low."
}
```

---

### 5. Deep research

```bash
curl -X POST http://localhost:8000/research/deep \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Compare Base L2 vs Arbitrum yield opportunities for stablecoin holders"
  }'
```

```json
{
  "result": "Base L2 vs Arbitrum — Stablecoin Yield Analysis\n\nBase L2:\n- TVL: $8.2B (+120% YTD)\n- Top protocols: Aerodrome (8.1% USDC APY), Moonwell (5.3%)\n- Bridge risk: low (Coinbase-backed)\n\nArbitrum:\n- TVL: $18.4B\n- Top protocols: GMX (7.2%), Radiant (9.1% with RDNT incentives)\n- More mature, higher liquidity depth\n\nRecommendation: Arbitrum for liquidity depth; Base for growth upside..."
}
```

---

### 6. Risk assessment

```bash
curl -X POST http://localhost:8000/assess-risk \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001"
  }'
```

```json
{
  "user_id": "user_001",
  "risk_level": "high",
  "risk_score": 8,
  "concentration_risk": "high",
  "liquidity_risk": "medium",
  "allowed_actions": ["view", "trade", "rebalance", "withdraw"],
  "can_trade": true,
  "can_withdraw": true,
  "recommendations": [
    "Reduce BTC concentration from 42% to under 30%",
    "Add stablecoin position for downside protection",
    "Consider ETH staking for passive yield"
  ]
}
```

---

### 7. Multi-agent research → trade signal

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Research ETH liquid staking yields. If the opportunity looks strong, act on it.",
    "user_id": "user_001"
  }'
```

```json
{
  "research": "ETH Liquid Staking Analysis:\n\nCurrent yields: Lido stETH 3.8% APY, Rocket Pool rETH 4.1% APY...\nRisk profile: low-medium. Both protocols battle-tested, $30B+ TVL combined.",
  "signal_triggered": true,
  "execution_result": {
    "status": "executed",
    "direction": "buy",
    "coin": "ETH",
    "amount_usd": 500.0,
    "coins_traded": 0.135,
    "portfolio": { ... }
  }
}
```

---

### 8. Gas fees

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the current Ethereum gas fees? I want to swap $10,000 to stETH.",
    "user_id": "user_001"
  }'
```

```json
{
  "reply": "Current Ethereum gas fees:\n- Slow: 12 gwei (~$0.80 for a simple transfer)\n- Normal: 18 gwei (~$1.20)\n- Fast: 25 gwei (~$1.65)\n\nFor a $10,000 stETH swap via Lido (more complex transaction), estimated cost at normal speed: $4.20–$6.80 depending on contract complexity. Recommend waiting for off-peak hours if not urgent."
}
```

---

## Configuration

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o) |
| `ETHERSCAN_API_KEY` | Etherscan key for gas data (optional) |
| `ANALYTICS_SERVICE_URL` | Internal analytics service endpoint |

## Demo Users

| User ID | Profile | Holdings |
|---|---|---|
| `user_001` | Alice Chen — moderate risk | 0.45 BTC, 3.2 ETH, 80 SOL, $16k cash |
| `user_002` | Bob Martinez — aggressive | 1.2 BTC, 5 ETH, $8.5k cash |
| `user_003` | Carol Williams — conservative | 0.1 BTC, $42k cash |
