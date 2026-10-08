export function recoveryErrorMessage(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason)
  if (
    message.includes('transcript_sha256') ||
    message.includes('does not match the transcript snapshot') ||
    message.includes("remote method 'recovery:restore'")
  ) {
    return 'La copia automática fue creada con un formato anterior y no pudo verificarse. El proyecto guardado sigue intacto; reinicia CREAcut y vuelve a intentar Recuperar.'
  }
  return message.split('\n', 1)[0]
}

