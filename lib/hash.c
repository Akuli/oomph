#include "oomph.h"
#include <stdio.h>
#include <openssl/evp.h>

// TODO: accept arbitrary binary data instead of utf-8 strings
struct class_Str oomph_hash(struct class_Str data, struct class_Str algname)
{
	char *algnamestr = string_to_cstr(algname);
	const EVP_MD *alg = EVP_get_digestbyname(algnamestr);
	if (!alg)
		panic_printf("unknown hash algorithm name: %s", algnamestr);
	free(algnamestr);

	unsigned nbytes;
	unsigned char hash[EVP_MAX_MD_SIZE];

	EVP_MD_CTX *ctx = EVP_MD_CTX_new();
	if (!ctx)
		panic_printf("EVP_MD_CTX_new failed");
	if (!EVP_DigestInit(ctx, alg))
		panic_printf("EVP_DigestInit failed");
	if (!EVP_DigestUpdate(ctx, string_data(data), data.nbytes))
		panic_printf("EVP_DigestUpdate failed");
	if (!EVP_DigestFinal(ctx, hash, &nbytes))
		panic_printf("EVP_DigestFinal failed");
	EVP_MD_CTX_free(ctx);

	char hex[2*EVP_MAX_MD_SIZE + 1];
	for (unsigned i = 0; i < nbytes; i++)
		sprintf(hex + 2*i, "%02x", hash[i]);
	return cstr_to_string(hex);
}
