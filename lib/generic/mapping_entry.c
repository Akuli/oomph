void ENTRY_DECREF(ENTRY e)
{
	if (e.hash != 0) {
		KEY_DECREF(e.key);
		VALUE_DECREF(e.value);
	}
}

void ENTRY_INCREF(ENTRY e)
{
	if (e.hash != 0) {
		KEY_INCREF(e.key);
		VALUE_INCREF(e.value);
	}
}

bool METHOD(equals)(ENTRY a, ENTRY b)
{
	return a.hash == b.hash && KEY_METHOD(equals)(a.key, b.key) && VALUE_METHOD(equals)(a.value, b.value);
}

struct class_Str METHOD(to_string)(ENTRY e)
{
	struct class_Str keystr = KEY_METHOD(to_string)(e.key);
	struct class_Str valstr = VALUE_METHOD(to_string)(e.value);

	struct class_Str res = cstr_to_string("MappingItem(");
	oomph_string_concat_inplace(&res, keystr);
	oomph_string_concat_inplace_cstr(&res, ": ");
	oomph_string_concat_inplace(&res, valstr);
	oomph_string_concat_inplace_cstr(&res, ")");

	string_decref(keystr);
	string_decref(valstr);
	return res;
}
