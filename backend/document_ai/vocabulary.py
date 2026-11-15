"""Skill names that PII detection must never mask (spaCy sometimes tags them as people or places)."""

TECH_TERMS: frozenset[str] = frozenset(
    term.lower()
    for term in """
Python Java JavaScript TypeScript Go Golang Rust Kotlin Swift Scala Ruby PHP Perl C C++ C# R MATLAB Julia SQL NoSQL
Django Flask FastAPI Celery Pandas NumPy SciPy PyTorch TensorFlow Keras JAX scikit-learn Spark PySpark Hadoop Kafka
Airflow dbt Snowflake BigQuery Redshift Databricks Postgres PostgreSQL MySQL MariaDB Oracle SQLite MongoDB Redis
Cassandra DynamoDB Elasticsearch OpenSearch Neo4j pgvector Pinecone Weaviate Qdrant Milvus Chroma FAISS
React Angular Vue Svelte Next.js Node Node.js Express NestJS Spring SpringBoot Hibernate Rails Laravel .NET ASP.NET
HTML CSS Sass Tailwind Bootstrap Redux GraphQL REST gRPC WebSockets OAuth OIDC SAML JWT Keycloak Okta
AWS Azure GCP Lambda EC2 S3 ECS EKS Fargate CloudFormation Terraform Pulumi Ansible Chef Puppet Docker Kubernetes
Helm ArgoCD Jenkins GitHub GitLab Bitbucket CircleCI Linux Unix Bash PowerShell Nginx Apache Prometheus Grafana
Loki Tempo Jaeger OpenTelemetry Datadog Splunk Sentry Kibana Logstash
LangChain LangGraph LlamaIndex OpenAI Anthropic Claude Llama Mistral Gemini Ollama vLLM HuggingFace Transformers
RAG LLM LLMs NLP MLOps MLflow Kubeflow SageMaker Vertex Bedrock DeepEval Ragas Langfuse
Agile Scrum Kanban Jira Confluence Figma Selenium Playwright Cypress Jest Vitest Pytest JUnit Postman
Tableau PowerBI Looker Excel SAP Salesforce Workday ServiceNow
""".split()
)
