# Gerenciador de tarefas Python

Desenvolver um pequeno gerenciador de tarefas Python com biblioteca padrão e CLI, sem serviços externos.

Cadastro com ID único, listagem de pendentes e concluídas, conclusão idempotente e exclusão lógica. Persistência JSON em caminho fornecido pelo usuário da CLI, escrita atômica, sem apagar registros. JSON inválido deve gerar erro claro sem sobrescrever os dados. CLI com add, list, complete e delete. Testes unittest em diretório temporário e documentação com exemplos.

Todos os arquivos da implementação devem permanecer no workspace desta missão. Não executar operações destrutivas, push ou deploy. Testes não devem tocar dados reais.
