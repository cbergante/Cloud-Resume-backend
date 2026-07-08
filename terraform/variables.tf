variable "resource_group_name" {
  type    = string
  default = "rg-cloudresume-api"
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "storage_account_name" {
  type    = string
  default = "stcrapifunc"
}

variable "function_app_name" {
  type    = string
  default = "fa-resumechallenge"
}

variable "cosmosdb_account_name" {
  type    = string
  default = "dbresumechallenge"
}

variable "cosmosdb_table_name" {
  type    = string
  default = "VisitorCounter"
}