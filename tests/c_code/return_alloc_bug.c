struct class_Foo {
	REFCOUNT_HEADER
	
};
struct class_Foo *ctor_Foo() {
	struct class_Foo *obj = malloc(sizeof(*obj));
	obj->refcount = 1;
	return obj;
}
struct class_Foo *var_bar(void){
	void *retval = NULL;
	void *ref0 = NULL;
	void *ref1 = NULL;
	struct class_Foo *var_f1 = (ref0 = (ctor_Foo()));
	struct class_Foo *var_f2 = (ref1 = (ctor_Foo()));
	retval = var_f2;incref(retval);goto out;
	out:
	if (ref1) decref(ref1);
	if (ref0) decref(ref0);
	(void)0;assert(retval); return retval;
	
}
void var_main(void){
	void *ref2 = NULL;
	decref((var_bar()));
	out:
	if (ref2) decref(ref2);
	(void)0;
}
