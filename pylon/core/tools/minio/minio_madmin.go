package main

//   Copyright 2020 getcarrier.io
//
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//
//       http://www.apache.org/licenses/LICENSE-2.0
//
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.

import "C"
import (
  "bytes"
  "encoding/hex"
  "github.com/minio/minio/pkg/madmin"
)

//export decrypt
func decrypt(secret_key *C.char, ciphertext_hex *C.char) *C.char {
  ciphertext, err := hex.DecodeString(C.GoString(ciphertext_hex))
  if err != nil {
    return C.CString("")
  }
  data, err := madmin.DecryptData(C.GoString(secret_key), bytes.NewReader(ciphertext))
  if err != nil {
    return C.CString("")
  }
  return C.CString(hex.EncodeToString(data))
}

//export encrypt
func encrypt(secret_key *C.char, cleartext_hex *C.char) *C.char {
  cleartext, err := hex.DecodeString(C.GoString(cleartext_hex))
  if err != nil {
    return C.CString("")
  }
  data, err := madmin.EncryptData(C.GoString(secret_key), cleartext)
  if err != nil {
    return C.CString("")
  }
  return C.CString(hex.EncodeToString(data))
}

func main() {}
