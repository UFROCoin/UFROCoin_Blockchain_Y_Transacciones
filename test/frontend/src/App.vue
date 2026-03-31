<template>
  <div class="container">
    <h1>UFROCoin PoC</h1>

    <div class="section">
      <h2>1. Autenticación y Generación de Wallet</h2>
      <input v-model="username" placeholder="Ingrese nombre de usuario" />
      <button @click="login">Generar Identidad</button>
      
      <p v-if="walletHash"><strong>Wallet Hash:</strong> {{ walletHash }}</p>
      <p v-if="token"><strong>JWT:</strong> {{ token.substring(0, 25) }}...</p>
    </div>

    <div class="section" v-if="token">
      <h2>2. Inserción Segura en MongoDB</h2>
      <input v-model="message" placeholder="Mensaje de prueba" />
      <button @click="saveData">Guardar Documento</button>
    </div>

    <div class="section">
      <h2>Log de Respuesta API</h2>
      <pre>{{ responseLog }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// --- Estado reactivo ---
const username = ref('')
const message = ref('')
const token = ref('')
const walletHash = ref('')
const responseLog = ref('Esperando acción...')

// --- Métodos de interacción con API ---
const login = async () => {
  try {
    const res = await fetch('http://localhost:8000/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value })
    })
    const data = await res.json()
    
    token.value = data.access_token
    walletHash.value = data.wallet_hash
    responseLog.value = JSON.stringify(data, null, 2)
  } catch (error) {
    responseLog.value = `Error de conexión: ${error.message}`
  }
}

const saveData = async () => {
  try {
    const res = await fetch('http://localhost:8000/test/db', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token.value}`
      },
      body: JSON.stringify({ message: message.value })
    })
    const data = await res.json()
    responseLog.value = JSON.stringify(data, null, 2)
  } catch (error) {
    responseLog.value = `Error de conexión: ${error.message}`
  }
}
</script>

<style scoped>
.container {
  font-family: system-ui, -apple-system, sans-serif;
  max-width: 600px;
  margin: 2rem auto;
  color: #333;
}
.section {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}
input {
  margin-right: 10px;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 8px 16px;
  background-color: #0056b3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:hover {
  background-color: #004494;
}
pre {
  background: #2d2d2d;
  color: #a3e4d7;
  padding: 15px;
  border-radius: 8px;
  overflow-x: auto;
}
</style>